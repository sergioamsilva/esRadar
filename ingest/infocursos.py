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
        escala = 100 if fica <= 1 else 1
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

    # Formas de ingresso dos novos inscritos (coortes recentes).
    for linha in tabela(caminho, "Formas Ingresso"):
        par = _par(linha)
        cna1 = _f(linha.get("PercentagemOpcao1ConcursoNacional"))
        if not par or cna1 is None:
            continue
        escala = 100 if cna1 <= 1 else 1

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


def atualizar(*, forcar: bool = False) -> Path:
    destino_xlsx = common.DIR_BRUTO / "infocursos" / f"Infocursos_{ANO_EDICAO}.xlsx"
    common.descarregar(
        f"{common.BASE_INFOCURSOS}/Infocursos_{ANO_EDICAO}.xlsx", destino_xlsx, forcar=forcar
    )
    dados = extrair(destino_xlsx)
    if len(dados) < 800:
        raise RuntimeError(f"só {len(dados)} pares extraídos do Infocursos — formato mudou?")
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
