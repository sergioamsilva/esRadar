"""Constrói data/out a partir dos dados brutos arquivados.

Junta três fontes com naturezas diferentes:
- resultados por fase (CSV extraídos dos XLS da DGES, 2018-2026): vagas,
  colocados, nota do último colocado e sobras, por par instituição/curso;
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


def _coluna(cabecalho: list[str], *prefixos: str) -> int | None:
    for i, nome in enumerate(cabecalho):
        limpo = " ".join(nome.split()).lower()
        for prefixo in prefixos:
            if limpo.startswith(prefixo.lower()):
                return i
    return None


def _int(valor: str) -> int | None:
    valor = valor.strip()
    return int(valor) if valor.isdigit() else None


def _nota(valor: str) -> float | None:
    valor = valor.strip().replace(",", ".")
    try:
        return round(float(valor), 1)
    except ValueError:
        return None


def ler_resultados() -> tuple[dict[str, dict[str, dict]], dict[str, str]]:
    """Séries por par: {par: {"{ano}f{fase}": {vagas, colocados, nota_ultimo, sobras}}}.

    O cabeçalho dos XLS muda entre anos e fases (colunas extra de desempate,
    «Vagas Iniciais 3F», «Sobras» vs «Vagas Sobrantes»), por isso o mapeamento
    é por nome de coluna, nunca por posição.

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
        with ficheiro.open(encoding="utf-8") as f:
            linhas = list(csv.reader(f))
        cab_idx = next(
            (i for i, l in enumerate(linhas) if any("Código Instit." in c for c in l)), None
        )
        if cab_idx is None:
            raise RuntimeError(f"{ficheiro}: cabeçalho não encontrado")
        cab = linhas[cab_idx]
        col = {
            "code": _coluna(cab, "código instit"),
            "codc": _coluna(cab, "código curso"),
            "curso": _coluna(cab, "nome do curso"),
            "vagas": _coluna(cab, "vagas iniciais"),
            "colocados": _coluna(cab, "colocados"),
            "nota": _coluna(cab, "nota do últ"),
            "sobras": _coluna(cab, "sobras", "vagas sobrantes"),
        }
        if None in (col["code"], col["codc"], col["colocados"], col["nota"]):
            raise RuntimeError(f"{ficheiro}: colunas em falta no cabeçalho {cab}")
        n = 0
        for linha in linhas[cab_idx + 1 :]:
            if len(linha) <= col["nota"]:
                continue
            code = linha[col["code"]].strip()
            codc = linha[col["codc"]].strip()
            if not re.fullmatch(r"\d{4}", code) or not re.fullmatch(r"[A-Z0-9]\d{3}", codc):
                continue
            registo = {
                "colocados": _int(linha[col["colocados"]]),
                "nota_ultimo": _nota(linha[col["nota"]]),
            }
            if col["vagas"] is not None:
                registo["vagas"] = _int(linha[col["vagas"]])
            if col["sobras"] is not None and len(linha) > col["sobras"]:
                registo["sobras"] = _int(linha[col["sobras"]])
            par = f"{code}-{codc}"
            series[par][f"{ano}f{fase}"] = registo
            if col["curso"] is not None and ano >= nomes.get(par, (0, ""))[0]:
                nomes[par] = (ano, linha[col["curso"]].strip())
            n += 1
        if n < 500:
            raise RuntimeError(f"{ficheiro}: só {n} pares extraídos")
    return series, {par: nome for par, (_, nome) in nomes.items()}


def ler_guia() -> dict:
    caminho = common.DIR_BRUTO / "guias" / str(ANO_CORRENTE) / "guia.json"
    if not caminho.exists():
        raise RuntimeError(f"{caminho} não existe — correr ingest.guias")
    return json.loads(caminho.read_text(encoding="utf-8"))


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
        for chave, registo in ficha_guia.get("series", {}).items():
            for k, v in registo.items():
                if k in ("candidatos", "candidatos_1opcao", "colocados_1opcao",
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
                )
            },
            "vagas_2026": ficha_guia.get("vagas"),
            "series": dict(sorted(serie.items())),
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
                "vagas": vagas,
                "nota_2026f1": f1_atual.get("nota_ultimo"),
                "nota_2025f1": f1_anterior.get("nota_ultimo"),
                "colocados_2026f1": f1_atual.get("colocados"),
                "sobras_2026f1": f1_atual.get("sobras"),
                "candidatos_1opcao_2025f1": procura,
                "racio_procura": round(procura / vagas, 2) if procura and vagas else None,
            }
        )

    # Agregados por estabelecimento e nacional.
    por_inst: dict[str, dict] = defaultdict(lambda: {"cursos": [], "vagas": 0, "colocados_f1": 0, "sobras_f1": 0})
    nacional_anos: dict[int, dict] = defaultdict(lambda: {"vagas_f1": 0, "colocados": 0, "pares": 0})
    for par, ficha in fichas.items():
        for chave, registo in ficha["series"].items():
            ano, fase = int(chave[:4]), int(chave[-1])
            if fase == 1 and registo.get("vagas") is not None:
                nacional_anos[ano]["vagas_f1"] += registo["vagas"]
                nacional_anos[ano]["pares"] += 1
            if registo.get("colocados"):
                nacional_anos[ano]["colocados"] += registo["colocados"]
        if not ficha["ativo"] or ficha["concurso"] != "Nacional":
            continue
        agg = por_inst[ficha["code"]]
        agg["cursos"].append(par)
        f1 = ficha["series"].get(f"{ANO_CORRENTE}f1", {})
        agg["vagas"] += ficha["vagas_2026"] or 0
        agg["colocados_f1"] += f1.get("colocados") or 0
        agg["sobras_f1"] += f1.get("sobras") or 0

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
        common.DIR_SAIDA / "nacional.json",
        {
            "fontes": [
                "DGES — resultados do CNA por fase (2018-2026, via Arquivo.pt até 2025)",
                "DGES — guia da candidatura 2026",
            ],
            "anos": {str(a): v for a, v in sorted(nacional_anos.items())},
        },
    )
    _escrever(
        common.DIR_SAIDA / "epoca.json",
        {
            "ano": ANO_CORRENTE,
            "fases_arquivadas": sorted(
                int(p.name.removeprefix("fase"))
                for p in (common.DIR_BRUTO / "coloc" / str(ANO_CORRENTE)).glob("fase*")
                if any(p.glob("cna*_resultados.csv"))
            ),
        },
    )
    print(
        f"build: {len(fichas)} fichas ({len(indice)} ativas), {len(saida_inst)} estabelecimentos, "
        f"{len(validacoes_falhadas)} divergências guia↔XLS"
    )


if __name__ == "__main__":
    try:
        construir()
    except RuntimeError as erro:
        sys.exit(f"erro: {erro}")
