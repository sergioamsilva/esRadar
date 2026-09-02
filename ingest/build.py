"""Constrói data/out a partir dos dados brutos arquivados.

Junta três fontes com naturezas diferentes:
- resultados por fase (CSV extraídos dos XLS/ODS da DGES, 1997-2026): vagas,
  colocados, nota do último colocado e sobras, por par instituição/curso
  (1997-1999 trazem ainda candidatos e médias dos colocados);
- guia da candidatura (guia.json): metadados do par (provas, fórmula, CNAEF)
  e a procura — candidatos, candidatos em 1ª opção, médias dos colocados —
  dos três anos anteriores;
- reference/instituicoes.yaml: crosswalk curado dos estabelecimentos.

Escreve JSON determinístico (chaves ordenadas, floats arredondados) para que
o git diff de data/out seja revisível por humanos.

Uso: python -m ingest.build
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

from . import common

ANO_CORRENTE = 2026
# Horizonte do portal: a DGES publica os resultados por par desde 1997 (1ª
# fase; 2ª desde 2004, 3ª desde 2012) — ver ingest.historico.
ANO_MINIMO = 1997

# Instituições-mãe que se fundiram: para comparar vagas ao longo de 30 anos,
# o grupo antigo conta no sucessor. Só fusões completas (2013: UL + UTL).
GRUPOS_SUCESSORES = {"Universidade Técnica de Lisboa": "Universidade de Lisboa"}


def _limpo(nome: str) -> str:
    return " ".join(nome.split()).lower()


def _coluna(cabecalho: list[str], *prefixos: str, exatos: tuple[str, ...] = ()) -> int | None:
    for i, nome in enumerate(cabecalho):
        limpo = _limpo(nome)
        if limpo in exatos:
            return i
        for prefixo in prefixos:
            if limpo.startswith(prefixo.lower()):
                return i
    return None


# Rótulos genéricos da segunda linha de cabeçalho dos ficheiros de 1997-1999
# («Candidatos» / «Colocados» / «Médias dos colocados» em cima, «Total» /
# «1ª op.» / «Nota» / «PI» / «12º» em baixo).
_SUBCABECALHOS = {"total", "1ª op.", "nota", "pi", "12º"}


def _cabecalho(linhas: list[list[str]]) -> tuple[int, list[str]]:
    """Localiza a linha de cabeçalho e devolve-a já fundida com a linha de
    grupos acima dela (só relevante nos ficheiros de duas linhas)."""
    for i, linha in enumerate(linhas):
        celulas = [_limpo(c) for c in linha]
        if any(c.startswith(("código instit", "código estab", "código da instit", "cód. estab")) for c in celulas) or (
            "estab" in celulas and "curso" in celulas and "ano" in celulas
        ):
            grupos = linhas[i - 1] if i > 0 else []
            fundido, grupo = [], ""
            for j, celula in enumerate(linha):
                if j < len(grupos) and grupos[j].strip():
                    grupo = " ".join(grupos[j].split())
                sub = " ".join(celula.split())
                if not sub:
                    fundido.append(grupo)
                elif grupo and sub.lower() in _SUBCABECALHOS:
                    fundido.append(f"{grupo} {sub}")
                else:
                    fundido.append(sub)
            return i, fundido
    raise RuntimeError("cabeçalho não encontrado")


def _int(valor: str) -> int | None:
    valor = valor.strip()
    return int(valor) if valor.isdigit() else None


def _nota(valor: str) -> float | None:
    valor = valor.strip().replace(",", ".")
    try:
        return round(float(valor), 1)
    except ValueError:
        return None


def ler_ficheiro_resultados(ficheiro: Path, ano: int, fase: int) -> list[tuple[str, dict, str | None]]:
    """Regista (par, registo, nome do curso) de um CSV de resultados.

    O cabeçalho muda entre anos e fases — quatro gerações (1997-99, 2000-11,
    2012-17, 2018+; ver reference/NOTAS.md) mais variantes por fase — por
    isso o mapeamento é por nome de coluna, nunca por posição.
    """
    with ficheiro.open(encoding="utf-8") as f:
        linhas = list(csv.reader(f))
    try:
        cab_idx, cab = _cabecalho(linhas)
    except RuntimeError as erro:
        raise RuntimeError(f"{ficheiro}: {erro}") from None
    col = {
        "code": _coluna(cab, "código instit", "código estab", "código da instit", "cód. estab", exatos=("estab",)),
        "codc": _coluna(cab, "código curso", "código do curso", "cód. curso"),
        "curso": _coluna(cab, "nome do curso"),
        "vagas": _coluna(cab, "vagas iniciais", "vagas colocadas a concurso", "vagas 20", exatos=("vagas",)),
        "recolocacao": _coluna(
            cab,
            "vagas de recolo",  # «recolo- cação» em 2022
            "vagas libertadas por recolocação",
            "vagas criadas por recolocação",
            "vagas ocupadas na",
        ),
        "nota": _coluna(cab, "nota do últ", "nota de candidatura", "nota últ"),
        "sobras": _coluna(
            cab, "sobras", "vagas sobrantes", "vagas sobrant", "vagas não ocupadas", "vagas da 3.ª fase não", "vagas disponíveis"
        ),
        # Procura: só em 1997-1999 (total e 1ª opção) e 2007 (1ª opção);
        # médias dos colocados só em 1997-1999. Depois, só o guia.
        "candidatos": _coluna(cab, exatos=("candidatos total",)),
        "candidatos_1opcao": _coluna(cab, "candidatos 1º", exatos=("candidatos 1ª op.",)),
        "colocados_1opcao": _coluna(cab, exatos=("colocados 1ª op.",)),
        "media_candidatura": _coluna(cab, exatos=("médias dos colocados nota",)),
        "media_provas": _coluna(cab, exatos=("médias dos colocados pi",)),
        "media_secundario": _coluna(cab, exatos=("médias dos colocados 12º",)),
    }
    # 1997-99 («Estab», «Curso», «Nome do Curso») e 2013-15 («Código do
    # curso», «Curso»): o rótulo nu «Curso» é o código ou o nome consoante
    # o que já ficou preenchido.
    if col["codc"] is None:
        col["codc"] = _coluna(cab, exatos=("curso",))
    elif col["curso"] is None:
        col["curso"] = next((i for i, nome in enumerate(cab) if _limpo(nome) == "curso" and i != col["codc"]), None)
    # «Colocados» reparte-se por colunas de desempate («desemp.», «sem
    # class. final», «vaga adic.», «Adicionais» em 2007) consoante o
    # ano/fase — somam-se todas: é essa soma que bate com os totais
    # anunciados pela DGES. «Vaga adic.» (vagas criadas, não colocados) e
    # «Colocados 1ª op.» (subconjunto, guardado à parte) ficam de fora.
    cols_colocados = [
        i
        for i, nome in enumerate(cab)
        if _limpo(nome).startswith(("colocados", "estudantes colocados", "adicionais")) and "1ª op" not in _limpo(nome)
    ]
    if None in (col["code"], col["codc"], col["nota"]) or not cols_colocados:
        raise RuntimeError(f"{ficheiro}: colunas em falta no cabeçalho {cab}")
    registos = []
    for linha in linhas[cab_idx + 1 :]:
        if len(linha) <= col["nota"]:
            continue
        code = linha[col["code"]].strip()
        codc = linha[col["codc"]].strip()
        if not re.fullmatch(r"\d{4}", code) or not re.fullmatch(r"[A-Z0-9]\d{3}", codc):
            continue
        parcelas = [_int(linha[i]) for i in cols_colocados if len(linha) > i and _int(linha[i]) is not None]
        # Nos ficheiros antigos, nota 0 significa «sem colocados pelo
        # contingente geral» (nota da própria DGES no ficheiro de 2000).
        registo = {
            "colocados": sum(parcelas) if parcelas else None,
            "nota_ultimo": _nota(linha[col["nota"]]) or None,
        }
        for campo in ("vagas", "recolocacao", "sobras", "candidatos", "candidatos_1opcao", "colocados_1opcao"):
            i = col[campo]
            if i is not None and len(linha) > i:
                registo["vagas_recolocacao" if campo == "recolocacao" else campo] = _int(linha[i])
        for campo in ("media_candidatura", "media_provas", "media_secundario"):
            i = col[campo]
            if i is not None and len(linha) > i:
                registo[campo] = _nota(linha[i]) or None
        # 2007 lista pares «objecto de concurso» sem vagas nem resultados:
        # linhas vazias não fazem série.
        if all(v is None for v in registo.values()):
            continue
        nome = linha[col["curso"]].strip() if col["curso"] is not None and len(linha) > col["curso"] else None
        registos.append((f"{code}-{codc}", registo, nome))
    return registos


def ler_resultados() -> tuple[dict[str, dict[str, dict]], dict[str, str]]:
    """Séries por par: {par: {"{ano}f{fase}": {vagas, colocados, nota_ultimo, sobras, …}}}.

    Devolve também o nome do curso mais recente de cada par, para dar nome às
    fichas de pares que já não existem no guia corrente.
    """
    series: dict[str, dict[str, dict]] = defaultdict(dict)
    nomes: dict[str, tuple[int, str]] = {}
    ficheiros = sorted(common.DIR_BRUTO.glob("coloc/*/fase*/cna*_resultados.csv"))
    if not ficheiros:
        raise RuntimeError("nenhum CSV de resultados em data/raw/coloc — correr ingest.arquivo")
    for ficheiro in ficheiros:
        ano = int(ficheiro.parts[-3])
        fase = int(ficheiro.parts[-2].removeprefix("fase"))
        registos = ler_ficheiro_resultados(ficheiro, ano, fase)
        if len(registos) < 500:
            raise RuntimeError(f"{ficheiro}: só {len(registos)} pares extraídos")
        for par, registo, nome in registos:
            series[par][f"{ano}f{fase}"] = registo
            if nome and ano >= nomes.get(par, (0, ""))[0]:
                nomes[par] = (ano, nome)
    return series, {par: nome for par, (_, nome) in nomes.items()}


def ler_guia() -> dict:
    caminho = common.DIR_BRUTO / "guias" / str(ANO_CORRENTE) / "guia.json"
    if not caminho.exists():
        raise RuntimeError(f"{caminho} não existe — correr ingest.guias")
    return json.loads(caminho.read_text(encoding="utf-8"))


def ler_series_guias_antigos() -> dict[str, dict[str, dict]]:
    """Séries das edições antigas do guia (Arquivo.pt), da mais velha para a
    mais recente — em sobreposição, a edição mais nova ganha, e o guia
    corrente (aplicado depois, em construir) ganha a todas."""
    series: dict[str, dict[str, dict]] = defaultdict(dict)
    for caminho in sorted(common.DIR_BRUTO.glob("guias/*/guia.json")):
        edicao = int(caminho.parent.name)
        if edicao >= ANO_CORRENTE:
            continue
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        for par, ficha in dados["pares"].items():
            for chave, registo in ficha.get("series", {}).items():
                series[par][chave] = registo
    return series


def slug(texto: str) -> str:
    """kebab-case sem acentos — TEM de bater com o slug() de site/src/lib/dados.ts."""
    import unicodedata

    t = unicodedata.normalize("NFD", texto)
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^a-z0-9]+", "-", t)
    return t.strip("-")


_PESO_SEC = re.compile(r"Média do secundário:\s*(\d+)\s*%")
_PESO_PROVAS = re.compile(r"Provas de ingresso:\s*(\d+)\s*%")


def pesos_formula(formula: str | None) -> dict | None:
    """Extrai os pesos da fórmula («Média do secundário: 50% / Provas: 50%»).

    Alimenta o simulador de nota no site; devolve None quando a fórmula não
    tem a forma canónica (pré-requisitos com peso, cursos artísticos) — o
    simulador simplesmente não aparece nesses cursos.
    """
    if not formula:
        return None
    sec = _PESO_SEC.search(formula)
    provas = _PESO_PROVAS.search(formula)
    if not sec or not provas:
        return None
    pesos = {"secundario": int(sec.group(1)), "provas": int(provas.group(1))}
    return pesos if pesos["secundario"] + pesos["provas"] == 100 else None


def _poligonos_distritos() -> list[tuple[str, list[list[tuple[float, float]]]]]:
    """Polígonos dos distritos no espaço projetado de data/mapa/continente.json."""
    mapa = json.loads((common.DIR_DADOS / "mapa" / "continente.json").read_text(encoding="utf-8"))
    distritos = []
    for p in mapa["paths"]:
        aneis = []
        for sub in p["d"].split("Z"):
            pontos = [
                (float(x), float(y))
                for x, y in re.findall(r"[ML]?\s*([\d.]+)[ ,]([\d.]+)", sub)
            ]
            if len(pontos) >= 3:
                aneis.append(pontos)
        distritos.append((p["n"], aneis))
    return distritos


# A MESMA projeção do mapa do site — equirretangular com a longitude
# corrigida por cos(lat média). Divergir aqui põe pontos no distrito errado.
_LON0, _LON1, _LAT0, _LAT1 = -9.6, -6.15, 36.9, 42.2
_X0 = _Y0 = 6.0


def _dentro(x: float, y: float, aneis: list[list[tuple[float, float]]]) -> bool:
    dentro = False
    for anel in aneis:
        j = len(anel) - 1
        for i in range(len(anel)):
            xi, yi = anel[i]
            xj, yj = anel[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                dentro = not dentro
            j = i
    return dentro


def atribuir_distritos(instituicoes: dict[str, dict]) -> None:
    """Preenche distrito por point-in-polygon; ilhas por gama de coordenadas."""
    import math

    distritos = _poligonos_distritos()
    k = math.cos(math.radians((_LAT0 + _LAT1) / 2))
    escala = min((340 - 2 * _X0) / ((_LON1 - _LON0) * k), (560 - 2 * _Y0) / (_LAT1 - _LAT0))
    for inst in instituicoes.values():
        geo = inst.get("geo")
        if inst.get("distrito") or not geo:
            continue
        lat, lon = geo["lat"], geo["lon"]
        if lon < -20:
            inst["distrito"] = "Açores"
            continue
        if lat < 34:
            inst["distrito"] = "Madeira"
            continue
        x = _X0 + (lon - _LON0) * k * escala
        y = _Y0 + (_LAT1 - lat) * escala
        for nome, aneis in distritos:
            if _dentro(x, y, aneis):
                inst["distrito"] = nome
                break
        else:
            # Pontos costeiros mesmo fora do traçado (ex.: Figueira da Foz):
            # fica o distrito com o vértice mais próximo.
            inst["distrito"] = min(
                distritos,
                key=lambda d: min((x - px) ** 2 + (y - py) ** 2 for anel in d[1] for px, py in anel),
            )[0]


def ler_etapas() -> dict[str, dict[str, list[dict]]]:
    """Notas por contingente da época corrente: {par: {"{ano}f{fase}": [...]}}."""
    etapas: dict[str, dict[str, list[dict]]] = defaultdict(dict)
    for listas in sorted(common.DIR_BRUTO.glob(f"coloc/{ANO_CORRENTE}/fase*/listas.json")):
        dados = json.loads(listas.read_text(encoding="utf-8"))
        chave = f"{dados['ano']}f{dados['fase']}"
        for code, cursos in dados.get("etapas", {}).items():
            for codc, lista in cursos.items():
                etapas[f"{code}-{codc}"][chave] = lista
    return etapas


def ler_infocursos() -> dict[str, dict]:
    caminho = common.DIR_BRUTO / "infocursos" / "infocursos.json"
    if not caminho.exists():
        return {}
    return json.loads(caminho.read_text(encoding="utf-8"))["pares"]


def ler_instituicoes() -> dict[str, dict]:
    dados = yaml.safe_load((common.DIR_REFERENCIA / "instituicoes.yaml").read_text(encoding="utf-8"))
    return {e["code"]: e for e in dados["estabelecimentos"]}


def _escrever(caminho: Path, dados: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps(dados, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def construir() -> None:
    resultados, nomes_historicos = ler_resultados()
    guia = ler_guia()
    instituicoes = ler_instituicoes()
    infocursos = ler_infocursos()
    etapas = ler_etapas()
    series_antigas = ler_series_guias_antigos()
    atribuir_distritos(instituicoes)
    pares_guia = guia["pares"]

    orfaos = [p for p in resultados if p.split("-")[0] not in instituicoes]
    if orfaos:
        raise RuntimeError(f"{len(orfaos)} pares com estabelecimento fora do crosswalk: {orfaos[:8]}")

    # Fichas por par: universo = guia corrente ∪ pares com resultados históricos.
    validacoes_falhadas = []
    fichas: dict[str, dict] = {}
    for par in sorted(set(resultados) | set(pares_guia)):
        code = par.split("-")[0]
        ficha_guia = pares_guia.get(par, {})
        serie: dict[str, dict] = defaultdict(dict)
        for chave, registo in resultados.get(par, {}).items():
            serie[chave].update({k: v for k, v in registo.items() if v is not None})
        # Edições antigas do guia (Arquivo.pt): só os campos que os XLS não
        # têm — procura, sexo, médias. Nota e colocados ficam dos XLS.
        for chave, registo in series_antigas.get(par, {}).items():
            if int(chave[:4]) < ANO_MINIMO:
                continue
            for k, v in registo.items():
                if v is not None and k not in serie[chave] and k not in ("vagas", "nota_ultimo", "colocados"):
                    serie[chave][k] = v
        for chave, registo in ficha_guia.get("series", {}).items():
            for k, v in registo.items():
                if k in ("candidatos", "candidatos_1opcao", "colocados_1opcao",
                         "candidatos_mulheres", "candidatos_homens",
                         "colocados_mulheres", "colocados_homens",
                         "media_candidatura", "media_provas", "media_secundario"):
                    serie[chave][k] = v
                elif k == "nota_ultimo" and chave in serie and "nota_ultimo" in serie[chave]:
                    # Validação cruzada guia ↔ XLS da época, quando ambos existem.
                    if abs(serie[chave]["nota_ultimo"] - v) > 0.1:
                        validacoes_falhadas.append((par, chave))
        inst = instituicoes[code]
        fichas[par] = {
            "par": par,
            "code": code,
            "codc": par.split("-", 1)[1],
            "curso": ficha_guia.get("curso"),
            "instituicao": inst["nome"],
            "grupo": inst["grupo"],
            "subsistema": inst["subsistema"],
            "ativo": par in pares_guia,
            # Só o concurso Nacional entra nos índices e somas — o guia também
            # lista pares de concursos institucionais e locais, fora do CNA.
            "concurso": ficha_guia.get("concurso"),
            **{
                k: ficha_guia.get(k)
                for k in (
                    "grau", "cnaef", "cnaef_nome", "duracao", "ects", "tipo_ensino",
                    "provas_ingresso", "formula", "minimo_candidatura", "minimo_provas",
                    "preferencia_regional", "acessos_preferenciais_pct",
                )
            },
            "vagas_2026": ficha_guia.get("vagas"),
            "formula_pesos": pesos_formula(ficha_guia.get("formula")),
            "distrito": inst.get("distrito"),
            "series": dict(sorted(serie.items())),
            "contingentes": etapas.get(par) or None,
            "infocursos": infocursos.get(par),
        }
        if fichas[par]["curso"] is None:
            # Par sem oferta em 2026: o nome vem do CSV mais recente onde apareceu.
            fichas[par]["curso"] = nomes_historicos.get(par) or f"[curso {par.split('-', 1)[1]}]"
    if len(validacoes_falhadas) > len(fichas) * 0.02:
        raise RuntimeError(
            f"nota_ultimo diverge entre guia e XLS em {len(validacoes_falhadas)} pares: "
            f"{validacoes_falhadas[:8]}"
        )

    # Derivados sobre o universo CNA: posição no país (percentil da nota de
    # corte), fidelidade da colocação (% dos colocados que tinham o curso em
    # 1ª opção) e vizinhos na mesma área CNAEF, ordenados por nota.
    cna = [f for f in fichas.values() if f["ativo"] and f["concurso"] == "Nacional"]
    notas_cna = sorted(
        f["series"].get(f"{ANO_CORRENTE}f1", {}).get("nota_ultimo")
        for f in cna
        if f["series"].get(f"{ANO_CORRENTE}f1", {}).get("nota_ultimo") is not None
    )
    por_area: dict[str, list[dict]] = defaultdict(list)
    for f in cna:
        if f["cnaef"]:
            por_area[f["cnaef"]].append(f)
    for lista in por_area.values():
        lista.sort(
            key=lambda f: f["series"].get(f"{ANO_CORRENTE}f1", {}).get("nota_ultimo") or -1,
            reverse=True,
        )
    for f in cna:
        nota = f["series"].get(f"{ANO_CORRENTE}f1", {}).get("nota_ultimo")
        if nota is not None and notas_cna:
            abaixo = sum(1 for n in notas_cna if n < nota)
            f["percentil_nota_2026"] = round(100 * abaixo / len(notas_cna))
        f1_ant = f["series"].get(f"{ANO_CORRENTE - 1}f1", {})
        if f1_ant.get("colocados") and f1_ant.get("colocados_1opcao") is not None:
            f["pct_colocados_1opcao_2025"] = round(
                100 * f1_ant["colocados_1opcao"] / f1_ant["colocados"]
            )
        vizinhos = por_area.get(f["cnaef"] or "", [])
        if len(vizinhos) > 1:
            i = vizinhos.index(f)
            recorte = vizinhos[max(0, i - 3) : i + 4]
            f["semelhantes"] = [
                {
                    "par": v["par"],
                    "curso": v["curso"],
                    "grupo": v["grupo"],
                    "nota": v["series"].get(f"{ANO_CORRENTE}f1", {}).get("nota_ultimo"),
                    "vagas": v["vagas_2026"],
                }
                for v in recorte
                if v is not f
            ][:6]

    # Contexto de emprego: posição do desemprego IEFP de cada curso entre os
    # cursos do CNA com dados, e a mediana nacional para referência.
    taxas = sorted(
        f["infocursos"]["desemprego"]["taxa"]
        for f in cna
        if f.get("infocursos") and f["infocursos"].get("desemprego")
    )
    mediana_desemprego = taxas[len(taxas) // 2] if taxas else None
    for f in cna:
        blocos = f.get("infocursos") or {}
        if blocos.get("desemprego") and taxas:
            taxa = blocos["desemprego"]["taxa"]
            f["desemprego_percentil"] = round(100 * sum(1 for t in taxas if t < taxa) / len(taxas))

    # Índice plano para pesquisa e rankings — só pares ativos no guia corrente.
    indice = []
    for par, ficha in fichas.items():
        if not ficha["ativo"] or ficha["concurso"] != "Nacional":
            continue
        s = ficha["series"]
        f1_atual = s.get(f"{ANO_CORRENTE}f1", {})
        f1_anterior = s.get(f"{ANO_CORRENTE - 1}f1", {})
        vagas = ficha["vagas_2026"]
        procura = f1_anterior.get("candidatos_1opcao")
        indice.append(
            {
                "par": par,
                "curso": ficha["curso"],
                "instituicao": ficha["instituicao"],
                "grupo": ficha["grupo"],
                "subsistema": ficha["subsistema"],
                "grau": ficha["grau"],
                "cnaef": ficha["cnaef"],
                "cnaef_nome": ficha["cnaef_nome"],
                "distrito": ficha["distrito"],
                "vagas": vagas,
                "nota_2026f1": f1_atual.get("nota_ultimo"),
                "nota_2025f1": f1_anterior.get("nota_ultimo"),
                "colocados_2026f1": f1_atual.get("colocados"),
                "sobras_2026f1": f1_atual.get("sobras"),
                "candidatos_1opcao_2025f1": procura,
                "racio_procura": round(procura / vagas, 2) if procura and vagas else None,
                # Do Infocursos, para rankings e agregados sem abrir as fichas.
                "desemprego": (ficha.get("infocursos") or {}).get("desemprego", {}).get("taxa")
                if ficha.get("infocursos")
                else None,
                "fica_1ano": (ficha.get("infocursos") or {}).get("apos_1_ano", {}).get("fica")
                if ficha.get("infocursos")
                else None,
            }
        )

    # Género no acesso, 2025 1ª fase (o ano mais recente com candidatos por
    # sexo no guia): nacional, por área CNAEF e extremos por curso.
    ANO_GENERO = ANO_CORRENTE - 1
    gen_nacional = {"candidatos_mulheres": 0, "candidatos_homens": 0, "colocados_mulheres": 0, "colocados_homens": 0}
    gen_area: dict[str, dict] = defaultdict(
        lambda: {"candidatos_mulheres": 0, "candidatos_homens": 0, "colocados_mulheres": 0, "colocados_homens": 0, "cursos": 0}
    )
    gen_cursos = []
    for f in cna:
        registo = f["series"].get(f"{ANO_GENERO}f1", {})
        if registo.get("candidatos_mulheres") is None:
            continue
        area = f["cnaef_nome"] or "Sem área"
        gen_area[area]["cursos"] += 1
        for chave in gen_nacional:
            valor = registo.get(chave) or 0
            gen_nacional[chave] += valor
            gen_area[area][chave] += valor
        col_m = registo.get("colocados_mulheres") or 0
        col_h = registo.get("colocados_homens") or 0
        if col_m + col_h >= 20:
            gen_cursos.append(
                {
                    "par": f["par"],
                    "curso": f["curso"],
                    "grupo": f["grupo"],
                    "colocados": col_m + col_h,
                    "pct_mulheres": round(100 * col_m / (col_m + col_h)),
                }
            )
    gen_cursos.sort(key=lambda c: c["pct_mulheres"])
    _escrever(
        common.DIR_SAIDA / "genero.json",
        {
            "ano": ANO_GENERO,
            "fase": 1,
            "nacional": gen_nacional,
            "areas": [
                {
                    "area": area,
                    **valores,
                    "pct_mulheres_colocadas": round(
                        100 * valores["colocados_mulheres"]
                        / max(1, valores["colocados_mulheres"] + valores["colocados_homens"])
                    ),
                }
                for area, valores in sorted(gen_area.items())
                if valores["colocados_mulheres"] + valores["colocados_homens"] >= 100
            ],
            "cursos_mais_masculinos": gen_cursos[:8],
            "cursos_mais_femininos": gen_cursos[-8:][::-1],
        },
    )

    # Perfil de percentis (5 dimensões) — todos «% de cursos abaixo deste».
    def _percentis(chave: str, valor_de, *, inverso: bool = False) -> None:
        valores = sorted(v for v in (valor_de(f) for f in cna) if v is not None)
        if not valores:
            return
        for f in cna:
            v = valor_de(f)
            if v is None:
                continue
            abaixo = sum(1 for x in valores if x < v)
            pct = round(100 * abaixo / len(valores))
            f[chave] = 100 - pct if inverso else pct

    _percentis("percentil_procura", lambda f: (
        None
        if not (f["series"].get(f"{ANO_CORRENTE - 1}f1", {}).get("candidatos_1opcao") and f["vagas_2026"])
        else f["series"][f"{ANO_CORRENTE - 1}f1"]["candidatos_1opcao"] / f["vagas_2026"]
    ))
    _percentis("percentil_fica", lambda f: (f.get("infocursos") or {}).get("apos_1_ano", {}).get("fica"))
    _percentis("percentil_fidelidade", lambda f: f.get("pct_colocados_1opcao_2025"))

    # «A 2ª fase compensa?» + absorção das sobras — o histórico completo.
    deltas_2f: list[float] = []
    fases_por_ano: dict[int, dict] = defaultdict(lambda: {"n": 0, "sobe": 0, "deltas": []})
    absorcao_por_ano: dict[int, dict] = defaultdict(lambda: {"sobras_f1": 0, "colocados_f2": 0})
    for f in fichas.values():
        for ano in range(ANO_MINIMO, ANO_CORRENTE + 1):
            r1 = f["series"].get(f"{ano}f1", {})
            r2 = f["series"].get(f"{ano}f2", {})
            n1, n2 = r1.get("nota_ultimo"), r2.get("nota_ultimo")
            if n1 is not None and n2 is not None:
                delta = round(n2 - n1, 1)
                deltas_2f.append(delta)
                fases_por_ano[ano]["n"] += 1
                fases_por_ano[ano]["deltas"].append(delta)
                if delta > 0:
                    fases_por_ano[ano]["sobe"] += 1
            if r1.get("sobras"):
                absorcao_por_ano[ano]["sobras_f1"] += r1["sobras"]
            if r2.get("colocados"):
                absorcao_por_ano[ano]["colocados_f2"] += r2["colocados"]
    caixas_2f: dict[str, int] = defaultdict(int)
    for d in deltas_2f:
        caixas_2f[str(max(-12, min(12, int(round(d / 2) * 2))))] += 1
    _escrever(
        common.DIR_SAIDA / "fases.json",
        {
            "n": len(deltas_2f),
            "pct_sobe": round(100 * sum(1 for d in deltas_2f if d > 0) / max(1, len(deltas_2f))),
            "delta_mediano": sorted(deltas_2f)[len(deltas_2f) // 2] if deltas_2f else None,
            "caixas": caixas_2f,
            "por_ano": {
                str(a): {
                    "n": v["n"],
                    "pct_sobe": round(100 * v["sobe"] / v["n"]) if v["n"] else None,
                    "delta_mediano": sorted(v["deltas"])[len(v["deltas"]) // 2] if v["deltas"] else None,
                }
                for a, v in sorted(fases_por_ano.items())
            },
            "absorcao": {
                str(a): {
                    **v,
                    "taxa": round(100 * min(1, v["colocados_f2"] / v["sobras_f1"])) if v["sobras_f1"] else None,
                }
                for a, v in sorted(absorcao_por_ano.items())
                if v["sobras_f1"] and v["colocados_f2"]  # só anos com 2ª fase nos dados
            },
        },
    )

    # O radar de histórias: factos notáveis detetados por regras, para o
    # Panorama — reescrito a cada build, muda a cada fase arquivada.
    historias: list[dict] = []
    for f in cna:
        notas = {
            int(k[:4]): v["nota_ultimo"]
            for k, v in f["series"].items()
            if k.endswith("f1") and v.get("nota_ultimo") is not None
        }
        alvo = notas.get(ANO_CORRENTE)
        anteriores = {a: n for a, n in notas.items() if a < ANO_CORRENTE}
        rotulo = f"{f['curso']} — {f['grupo']}"
        caminho = f"/curso/{f['par']}-{slug(f['curso'])}/"
        if alvo is not None and anteriores:
            delta = alvo - notas.get(ANO_CORRENTE - 1, alvo)
            if len(anteriores) >= 4 and alvo > max(anteriores.values()) + 0.5:
                historias.append({"tipo": "recorde", "peso": alvo - max(anteriores.values()),
                                  "texto": f"{rotulo} fechou a {alvo:.1f} — o máximo da sua série desde {min(anteriores)}.",
                                  "url": caminho})
            if abs(delta) >= 25 and notas.get(ANO_CORRENTE - 1) is not None:
                historias.append({"tipo": "salto" if delta > 0 else "queda", "peso": abs(delta),
                                  "texto": f"{rotulo} {'saltou' if delta > 0 else 'caiu'} {abs(delta):.1f} pontos num ano ({notas[ANO_CORRENTE - 1]:.1f} → {alvo:.1f}).",
                                  "url": caminho})
        sobras = {
            int(k[:4]): v.get("sobras")
            for k, v in f["series"].items()
            if k.endswith("f1") and v.get("sobras") is not None
        }
        if (
            sobras.get(ANO_CORRENTE) == 0
            and len([a for a in sobras if a < ANO_CORRENTE]) >= 4
            and all(s > 0 for a, s in sobras.items() if a < ANO_CORRENTE)
        ):
            historias.append({"tipo": "esgotou", "peso": 20 + (f["vagas_2026"] or 0) / 10,
                              "texto": f"{rotulo} esgotou as vagas pela primeira vez em {len(sobras)} anos.",
                              "url": caminho})
        if alvo is not None and not anteriores and alvo >= 168:
            historias.append({"tipo": "estreia", "peso": alvo - 150,
                              "texto": f"{rotulo} estreou-se no concurso já a fechar em {alvo:.1f}.",
                              "url": caminho})
        c1 = f["series"].get(f"{ANO_CORRENTE - 1}f1", {}).get("candidatos_1opcao")
        c3 = f["series"].get(f"{ANO_CORRENTE - 3}f1", {}).get("candidatos_1opcao")
        if c1 is not None and c3 and c3 >= 40 and c1 <= c3 * 0.45:
            historias.append({"tipo": "fuga", "peso": (1 - c1 / c3) * 30,
                              "texto": f"{rotulo}: a procura em 1ª opção caiu de {c3} para {c1} em dois anos.",
                              "url": caminho})
    historias.sort(key=lambda h: h["peso"], reverse=True)
    _escrever(common.DIR_SAIDA / "historias.json", {"geradas_de": f"época {ANO_CORRENTE}", "historias": historias[:14]})

    # Agregados por estabelecimento, por grupo e nacional.
    por_inst: dict[str, dict] = defaultdict(lambda: {"cursos": [], "vagas": 0, "colocados_f1": 0, "sobras_f1": 0})
    nacional_anos: dict[int, dict] = defaultdict(
        lambda: {
            "vagas_f1": 0, "colocados": 0, "colocados_f1": 0, "colocados_f2": 0, "colocados_f3": 0, "pares": 0,
            "vagas_universitario": 0, "vagas_politecnico": 0,
        }
    )
    notas_ano: dict[int, list[float]] = defaultdict(list)
    grupos_ano: dict[str, dict[int, dict]] = defaultdict(lambda: defaultdict(lambda: {"vagas": 0, "colocados": 0}))
    for par, ficha in fichas.items():
        subsistema = ficha["subsistema"]
        grupo = GRUPOS_SUCESSORES.get(ficha["grupo"], ficha["grupo"])
        for chave, registo in ficha["series"].items():
            ano, fase = int(chave[:4]), int(chave[-1])
            if fase == 1 and registo.get("vagas") is not None:
                nacional_anos[ano]["vagas_f1"] += registo["vagas"]
                nacional_anos[ano]["pares"] += 1
                if subsistema:
                    nacional_anos[ano][f"vagas_{subsistema}"] += registo["vagas"]
                grupos_ano[grupo][ano]["vagas"] += registo["vagas"]
            if fase == 1 and registo.get("nota_ultimo") is not None:
                notas_ano[ano].append(registo["nota_ultimo"])
            if registo.get("colocados"):
                nacional_anos[ano]["colocados"] += registo["colocados"]
                nacional_anos[ano][f"colocados_f{fase}"] += registo["colocados"]
                if fase == 1:
                    grupos_ano[grupo][ano]["colocados"] += registo["colocados"]
        if not ficha["ativo"] or ficha["concurso"] != "Nacional":
            continue
        agg = por_inst[ficha["code"]]
        agg["cursos"].append(par)
        f1 = ficha["series"].get(f"{ANO_CORRENTE}f1", {})
        agg["vagas"] += ficha["vagas_2026"] or 0
        agg["colocados_f1"] += f1.get("colocados") or 0
        agg["sobras_f1"] += f1.get("sobras") or 0

    # Distribuição das notas de corte por ano — cada ano conta os seus
    # cursos, por isso atravessa as recodificações sem crosswalk.
    for ano, notas in notas_ano.items():
        notas.sort()
        q = lambda p: notas[int(p * (len(notas) - 1))]  # noqa: E731
        nacional_anos[ano]["notas"] = {
            "n": len(notas), "p10": q(0.1), "p50": q(0.5), "p90": q(0.9),
            "acima_170": sum(1 for n in notas if n >= 170),
        }

    saida_inst = []
    for code, agg in sorted(por_inst.items()):
        inst = instituicoes[code]
        saida_inst.append(
            {
                "code": code,
                "nome": inst["nome"],
                "grupo": inst["grupo"],
                "subsistema": inst["subsistema"],
                "distrito": inst.get("distrito"),
                "geo": inst.get("geo"),
                "n_cursos": len(agg["cursos"]),
                "vagas": agg["vagas"],
                "colocados_f1": agg["colocados_f1"],
                "sobras_f1": agg["sobras_f1"],
                "ocupacao_f1": round(agg["colocados_f1"] / agg["vagas"], 3) if agg["vagas"] else None,
            }
        )

    # Escrita. Limpa fichas de pares que deixaram de existir.
    dir_par = common.DIR_SAIDA / "par"
    if dir_par.exists():
        for antigo in dir_par.glob("*.json"):
            if antigo.stem not in fichas:
                antigo.unlink()
    for par, ficha in fichas.items():
        _escrever(dir_par / f"{par}.json", ficha)
    _escrever(common.DIR_SAIDA / "cursos.json", {"gerado_de": "guia 2026 + resultados CNA", "cursos": indice})
    _escrever(common.DIR_SAIDA / "instituicoes.json", {"instituicoes": saida_inst})
    _escrever(
        common.DIR_SAIDA / "grupos.json",
        {
            "nota": "Vagas e colocados da 1ª fase por instituição-mãe e ano; a Universidade "
            "Técnica de Lisboa conta como Universidade de Lisboa (fusão de 2013).",
            "grupos": [
                {"grupo": g, "anos": {str(a): v for a, v in sorted(anos.items())}}
                for g, anos in sorted(grupos_ano.items())
            ],
        },
    )
    _escrever(
        common.DIR_SAIDA / "nacional.json",
        {
            "fontes": [
                "DGES — resultados do CNA por fase (1997-2017 da página de estatísticas; "
                "2018-2025 via Arquivo.pt; 2026 arquivado na época)",
                "DGES — guia da candidatura 2026",
                "Infocursos (MECI) — edição 2026",
            ],
            "mediana_desemprego_cursos": mediana_desemprego,
            "anos": {str(a): v for a, v in sorted(nacional_anos.items())},
        },
    )
    _escrever(
        common.DIR_SAIDA / "epoca.json",
        {
            "ano": ANO_CORRENTE,
            "atualizado": __import__("datetime").date.today().isoformat(),
            "fases_arquivadas": sorted(
                int(p.name.removeprefix("fase"))
                for p in (common.DIR_BRUTO / "coloc" / str(ANO_CORRENTE)).glob("fase*")
                if any(p.glob("cna*_resultados.csv"))
            ),
        },
    )
    # Mapa de redirects dos URLs antigos (só código) para os novos com nome
    # no caminho — consumido por site/astro.config.mjs. Sem o prefixo base.
    redirects = {}
    for par, ficha in fichas.items():
        redirects[f"/curso/{par}"] = f"/curso/{par}-{slug(ficha['curso'])}/"
    for inst in saida_inst:
        redirects[f"/instituicao/{inst['code']}"] = (
            f"/instituicao/{inst['code']}-{slug(inst['nome'])}/"
        )
    _escrever(common.DIR_SAIDA / "redirects.json", redirects)

    print(
        f"build: {len(fichas)} fichas ({len(indice)} ativas), {len(saida_inst)} estabelecimentos, "
        f"{len(validacoes_falhadas)} divergências guia↔XLS"
    )


if __name__ == "__main__":
    try:
        construir()
    except RuntimeError as erro:
        sys.exit(f"erro: {erro}")
