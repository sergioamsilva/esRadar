"""Infocursos (MECI): estatísticas por curso, para lá do concurso.

A edição anual (Infocursos_{ano}.xlsx em infocursos.medu.pt) traz, por par
unidade orgânica/curso — as mesmas chaves code/codc da DGES:
- Percentil Entrada: percentil médio nacional dos colocados, 2020-2025;
- Desemprego Registado: % de recém-diplomados inscritos no IEFP;
- Inscritos por Sexo: composição do curso;
- Situacao Apos 1 Ano: quantos ficam, mudam ou desaparecem do sistema;
- Classificacoes Finais: nota média dos diplomados.

O XLSX declara mal a dimensão das folhas (o read_xlsx do DuckDB só vê a
primeira coluna), por isso lê-se o XML diretamente com a stdlib.

Uso: python -m ingest.infocursos
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from . import common

ANO_EDICAO = 2026
_M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _folhas(caminho: Path) -> tuple[zipfile.ZipFile, list[str]]:
    z = zipfile.ZipFile(caminho)
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    return z, [s.get("name") for s in wb.find(f"{_M}sheets")]


def _linhas(z: zipfile.ZipFile, indice: int):
    strings: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        ss = ET.fromstring(z.read("xl/sharedStrings.xml"))
        strings = ["".join(t.text or "" for t in si.iter(f"{_M}t")) for si in ss.findall(f"{_M}si")]
    folha = ET.fromstring(z.read(f"xl/worksheets/sheet{indice}.xml"))
    for row in folha.iter(f"{_M}row"):
        celulas: dict[str, str] = {}
        for c in row:
            v = c.find(f"{_M}v")
            if v is None or v.text is None:
                continue
            coluna = re.match(r"[A-Z]+", c.get("r")).group(0)
            celulas[coluna] = strings[int(v.text)] if c.get("t") == "s" else v.text
        yield celulas


def tabela(caminho: Path, folha: str) -> list[dict[str, str]]:
    """Linhas da folha como dicts nome-de-coluna → valor (cabeçalho real
    é a linha que começa por «Estabelecimento»)."""
    z, nomes = _folhas(caminho)
    if folha not in nomes:
        raise RuntimeError(f"folha «{folha}» não existe em {caminho.name} ({nomes})")
    cabecalho: dict[str, str] | None = None
    registos = []
    for linha in _linhas(z, nomes.index(folha) + 1):
        if cabecalho is None:
            if linha.get("A") == "Estabelecimento":
                cabecalho = linha
            continue
        if not linha:
            continue
        registos.append({cabecalho[c]: v for c, v in linha.items() if c in cabecalho})
    if cabecalho is None:
        raise RuntimeError(f"{caminho.name}/{folha}: cabeçalho não encontrado")
    return registos


def _f(valor: str | None) -> float | None:
    if valor is None or valor == "":
        return None
    try:
        return float(valor)
    except ValueError:
        return None


def _i(valor: str | None) -> int | None:
    f = _f(valor)
    return int(f) if f is not None else None


def _par(linha: dict) -> str | None:
    code = (linha.get("CodigoUnidadeOrganica") or "").strip()
    codc = (linha.get("CodigoCurso") or "").strip()
    if re.fullmatch(r"\d{4}", code) and re.fullmatch(r"[A-Z0-9]\d{3}", codc):
        return f"{code}-{codc}"
    return None


def extrair(caminho: Path) -> dict[str, dict]:
    dados: dict[str, dict] = {}

    def bloco(par: str) -> dict:
        return dados.setdefault(par, {})

    for linha in tabela(caminho, "Percentil Entrada"):
        par = _par(linha)
        if not par:
            continue
        serie = {}
        for chave, valor in linha.items():
            m = re.fullmatch(r"PercentilMedio(\d{4})", chave)
            if m and _f(valor) is not None:
                ano = m.group(1)
                serie[ano] = {
                    "percentil": round(_f(valor) * 100, 1),
                    "nota_ingresso_media": _f(linha.get(f"NotaIngressoMedia{ano}")),
                    "matriculados": _i(linha.get(f"NumeroMatriculadosCNA{ano}")),
                }
        if serie:
            bloco(par)["percentil_entrada"] = serie

    for linha in tabela(caminho, "Desemprego Registado"):
        par = _par(linha)
        taxa = _f(linha.get("TaxaDesempregoRegistadoCurso"))
        if not par or taxa is None:
            continue
        bloco(par)["desemprego"] = {
            "taxa": round(taxa * 100, 1) if taxa <= 1 else round(taxa, 1),
            "diplomados": _i(linha.get("NumeroDiplomadosCurso")),
            "periodo": linha.get("AnosLetivosDiplomados"),
        }

    # Inscritos por sexo: várias linhas por par (uma por ano letivo) — fica a
    # mais recente.
    for linha in tabela(caminho, "Inscritos por Sexo"):
        par = _par(linha)
        if not par or _i(linha.get("NumeroInscritos")) is None:
            continue
        atual = bloco(par).get("sexo")
        ano_letivo = linha.get("AnoLetivo") or ""
        if atual and atual["ano_letivo"] >= ano_letivo:
            continue
        bloco(par)["sexo"] = {
            "ano_letivo": ano_letivo,
            "inscritos": _i(linha.get("NumeroInscritos")),
            "homens": _i(linha.get("NumeroHomens")),
            "mulheres": _i(linha.get("NumeroMulheres")),
        }

    for linha in tabela(caminho, "Situacao Apos 1 Ano"):
        par = _par(linha)
        fica = _f(linha.get("PercentagemInscritosMesmoEstabelecimentoCurso"))
        if not par or fica is None:
            continue
        # A escala (frações 0-1 vs percentagens 0-100) decide-se pela SOMA
        # das parcelas — olhar só para a primeira falha quando ela é 0.
        soma = sum(
            _f(linha.get(c)) or 0
            for c in (
                "PercentagemInscritosMesmoEstabelecimentoCurso",
                "PercentagemOutroCursoMesmoEstabelecimento",
                "PercentagemNoutroEstabelecimento",
                "PercentagemNaoEncontradosEnsinoSuperior",
            )
        )
        escala = 100 if soma <= 1.5 else 1
        bloco(par)["apos_1_ano"] = {
            "coorte": linha.get("AnosInscritosPrimeiroAnoPrimeiraVez"),
            "novos_inscritos": _i(linha.get("NumeroInscritosPrimeiroAnoPrimeiraVez2Anos")),
            "fica": round(fica * escala, 1),
            "muda_curso": round((_f(linha.get("PercentagemOutroCursoMesmoEstabelecimento")) or 0) * escala, 1),
            "muda_estabelecimento": round((_f(linha.get("PercentagemNoutroEstabelecimento")) or 0) * escala, 1),
            "fora": round((_f(linha.get("PercentagemNaoEncontradosEnsinoSuperior")) or 0) * escala, 1),
        }

    for linha in tabela(caminho, "Classificacoes Finais"):
        par = _par(linha)
        media = _f(linha.get("NotaFinalMedia"))
        if not par or media is None:
            continue
        distribuicao = {}
        for nota in range(10, 21):
            pct = _f(linha.get(f"PercentagemNota{nota}"))
            if pct is not None:
                distribuicao[str(nota)] = round(pct * 100, 1) if pct <= 1 else round(pct, 1)
        bloco(par)["diplomados"] = {
            "nota_final_media": round(media, 1),
            "n": _i(linha.get("NumeroDiplomados2AnosRaides")),
            "periodo": linha.get("AnosObtencaoDiploma"),
            "distribuicao": distribuicao or None,
        }

    # Nacionalidade: como no sexo, fica o ano letivo mais recente.
    for linha in tabela(caminho, "Inscritos por Nacionalidade"):
        par = _par(linha)
        total = _i(linha.get("NumeroInscritos"))
        if not par or not total:
            continue
        atual = bloco(par).get("nacionalidade")
        ano_letivo = linha.get("AnoLetivo") or ""
        if atual and atual["ano_letivo"] >= ano_letivo:
            continue
        bloco(par)["nacionalidade"] = {
            "ano_letivo": ano_letivo,
            "inscritos": total,
            "estrangeiros": _i(linha.get("NumeroEstrangeiros")),
        }

    # Idades dos inscritos, condensadas em três escalões legíveis; fica o
    # ano letivo mais recente.
    for linha in tabela(caminho, "Inscritos por Idade"):
        par = _par(linha)
        total = _i(linha.get("NumeroTotalInscritos"))
        if not par or not total:
            continue
        atual = bloco(par).get("idades")
        ano_letivo = linha.get("AnoLetivo") or ""
        if atual and atual["ano_letivo"] >= ano_letivo:
            continue
        ate_19 = (_i(linha.get("Numero1_18Anos")) or 0) + (_i(linha.get("Numero19Anos")) or 0)
        de_20_a_23 = sum(_i(linha.get(f"Numero{a}Anos")) or 0 for a in (20, 21, 22, 23))
        bloco(par)["idades"] = {
            "ano_letivo": ano_letivo,
            "inscritos": total,
            "pct_ate_19": round(100 * ate_19 / total),
            "pct_20_a_23": round(100 * de_20_a_23 / total),
            "pct_24_ou_mais": max(0, 100 - round(100 * ate_19 / total) - round(100 * de_20_a_23 / total)),
        }

    # Série de inscritos totais por ano letivo (colunas «2020/2021»…).
    for linha in tabela(caminho, "Numero Inscritos"):
        par = _par(linha)
        if not par:
            continue
        serie = {
            chave: _i(valor)
            for chave, valor in linha.items()
            if re.fullmatch(r"\d{4}/\d{4}", chave) and _i(valor) is not None
        }
        if serie:
            bloco(par)["inscritos_serie"] = serie

    # Formas de ingresso dos novos inscritos (coortes recentes).
    _COLS_INGRESSO = (
        "PercentagemOpcao1ConcursoNacional",
        "PercentagemOpcao2ConcursoNacional",
        "PercentagemConcursoLocalouInstitucional",
        "PercentagemOutrosRegimeGeral",
        "PercentagemMudancaCurso",
        "PercentagemProvasMaiores23Anos",
        "PercentagemOutrosRegimes",
    )
    for linha in tabela(caminho, "Formas Ingresso"):
        par = _par(linha)
        cna1 = _f(linha.get("PercentagemOpcao1ConcursoNacional"))
        if not par or cna1 is None:
            continue
        soma = sum(_f(linha.get(c)) or 0 for c in _COLS_INGRESSO)
        if soma == 0:
            continue  # linha suprimida na fonte (tudo a zeros)
        escala = 100 if soma <= 1.5 else 1

        def pct(chave: str) -> float:
            return round((_f(linha.get(chave)) or 0) * escala, 1)

        bloco(par)["formas_ingresso"] = {
            "coorte": linha.get("AnosInscritosPrimeiroAnoPrimeiraVez"),
            "cna_1opcao": round(cna1 * escala, 1),
            "cna_outras": pct("PercentagemOpcao2ConcursoNacional"),
            "concurso_local": pct("PercentagemConcursoLocalouInstitucional"),
            "mudanca_curso": pct("PercentagemMudancaCurso"),
            "maiores_23": pct("PercentagemProvasMaiores23Anos"),
            "outros": round(pct("PercentagemOutrosRegimeGeral") + pct("PercentagemOutrosRegimes"), 1),
        }

    return dados


def serie_demografica(*, forcar: bool = False) -> dict[str, dict[str, dict]]:
    """A evolução de mulheres e estrangeiros por curso, cruzando edições.

    Cada edição anual do Infocursos só traz UM ano letivo nas folhas de
    sexo/nacionalidade (a edição Y traz (Y-2)/(Y-1)); a série constrói-se
    descarregando as edições de 2021 em diante.
    """
    serie: dict[str, dict[str, dict]] = {}
    for edicao in range(2021, ANO_EDICAO + 1):
        destino = common.DIR_BRUTO / "infocursos" / f"Infocursos_{edicao}.xlsx"
        try:
            common.descarregar(
                f"{common.BASE_INFOCURSOS}/Infocursos_{edicao}.xlsx", destino, forcar=forcar
            )
        except RuntimeError as erro:
            print(f"  aviso: edição {edicao} indisponível ({erro})")
            continue
        try:
            sexo = tabela(destino, "Inscritos por Sexo")
            nacionalidade = tabela(destino, "Inscritos por Nacionalidade")
        except RuntimeError as erro:
            print(f"  aviso: edição {edicao}: {erro}")
            continue
        estrangeiros = {
            (_par(l), l.get("AnoLetivo")): _i(l.get("NumeroEstrangeiros")) for l in nacionalidade
        }
        for linha in sexo:
            par = _par(linha)
            total = _i(linha.get("NumeroInscritos"))
            ano_letivo = linha.get("AnoLetivo") or ""
            if not par or not total or not ano_letivo:
                continue
            serie.setdefault(par, {})[ano_letivo] = {
                "inscritos": total,
                "mulheres": _i(linha.get("NumeroMulheres")),
                "estrangeiros": estrangeiros.get((par, ano_letivo)),
            }
    return serie


def atualizar(*, forcar: bool = False) -> Path:
    destino_xlsx = common.DIR_BRUTO / "infocursos" / f"Infocursos_{ANO_EDICAO}.xlsx"
    common.descarregar(
        f"{common.BASE_INFOCURSOS}/Infocursos_{ANO_EDICAO}.xlsx", destino_xlsx, forcar=forcar
    )
    dados = extrair(destino_xlsx)
    if len(dados) < 800:
        raise RuntimeError(f"só {len(dados)} pares extraídos do Infocursos — formato mudou?")
    for par, serie in serie_demografica(forcar=forcar).items():
        if len(serie) >= 2:
            dados.setdefault(par, {})["demografia_serie"] = dict(sorted(serie.items()))
    destino = common.DIR_BRUTO / "infocursos" / "infocursos.json"
    destino.write_text(
        json.dumps(
            {"edicao": ANO_EDICAO, "pares": dados}, ensure_ascii=False, indent=1, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"infocursos: {len(dados)} pares → {destino}")
    return destino


if __name__ == "__main__":
    atualizar()
