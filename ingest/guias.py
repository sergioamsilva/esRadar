"""Scraper do Guia da Candidatura da DGES (dges.gov.pt/guias).

O guia do ano corrente está sempre online e é a única fonte estruturada com
os metadados de cada par instituição/curso (provas de ingresso, fórmula,
mínimos, área CNAEF) e com a procura — candidatos por ano×fase, incluindo em
1ª opção — que os XLS de resultados da época não trazem.

O HTML bruto fica em data/raw/guias/{ano}/ e a extração em guia.json.
Reexecutar usa a cache em disco: só volta à rede com --forcar.

Uso: python -m ingest.guias [--forcar] [--limite N]
"""

from __future__ import annotations

import argparse
import json
import re
import string
import sys
from pathlib import Path

from . import common

ANO_GUIA = 2026

_CURSO = re.compile(
    r"<div class='lin-area-c1'>([^<]+)</div>"
    r"<div class='lin-area-c2'>([^<]+)</div>"
    r"<div class='lin-area-c3'>\[([^\]]+)\]</div>"
)
_PAR = re.compile(
    r"<div class='lin-curso-c2'>(\d{4})</div>"
    r"<div class='lin-curso-c3'><a href='detcursopi\.asp\?codc=([^&]+)&amp;code=\d{4}'[^>]*>([^<]+)</a></div>"
    r"<div class='lin-curso-c4'>(\d+)</div>"
)
_BLOCO = re.compile(r"<div class='box10'>|<div class='lin-curso'>")


def parse_indice(html: str) -> list[dict]:
    """Pares (curso, instituição, vagas) de uma página indcurso.asp?letra=X.

    O HTML é uma sequência plana: um bloco box10 abre um curso e os
    lin-curso seguintes são as instituições que o oferecem.
    """
    pares = []
    curso_atual: dict | None = None
    pos = 0
    while True:
        marcador = _BLOCO.search(html, pos)
        if not marcador:
            break
        pos = marcador.end()
        if marcador.group(0) == "<div class='box10'>":
            m = _CURSO.search(html, pos)
            curso_atual = (
                {"codc": m.group(1).strip(), "curso": m.group(2).strip(), "grau": m.group(3).strip()}
                if m and m.start() - pos < 20
                else None
            )
        elif curso_atual:
            m = _PAR.search(html, pos)
            if m and m.start() - pos < 80 and m.group(2).strip() == curso_atual["codc"]:
                pares.append(
                    {
                        **curso_atual,
                        "code": m.group(1),
                        "instituicao": m.group(3).strip(),
                        "vagas": int(m.group(4)),
                    }
                )
    return pares


_CAB = re.compile(r'class="cab1">([^<]+).*?class="cab2">([^<]+)', re.S)
# Campo a campo, porque o bloco de características não é estável: os
# «Preparatórios de Mestrado» não têm Duração/ECTS, e os cursos de concurso
# local (artes) intercalam texto explicativo — e às vezes nem têm vagas.
_CAMPOS = {
    "grau": re.compile(r"Grau: ([^<]+)<br>"),
    "cnaef_par": re.compile(r"Área CNAEF: (\d+) ([^<]+)<br>"),
    "duracao": re.compile(r"Duração: ([^<]+)<br>"),
    "ects": re.compile(r"ECTS: (\d+)<br>"),
    "tipo": re.compile(r"Tipo de Ensino: ([^<]+)<br>"),
    "concurso": re.compile(r"Concurso: ([^<]+)<br>"),
    "vagas": re.compile(r"Vagas para \d{4}-\d{4}: (\d+)"),
}
_MINIMOS = re.compile(
    r"Classificações Mínimas</h2>Nota de candidatura: (\d+)[^<]*<br>Provas de ingresso: (\d+)"
)
_FORMULA = re.compile(r"Fórmula de Cálculo</h2>(.*?)<a name", re.S)
_PROVAS = re.compile(r"Provas de Ingresso</h2>(.*?)<h2>", re.S)
_ANOS = re.compile(r'<th colspan="2" class="th1">(\d{4})</th>')
_LINHA_STATS = re.compile(r"<th class=\"tlab[^\"]*\"[^>]*>(.*?)</th>(.*?)</tr>", re.S)
_CELULA = re.compile(r"<td[^>]*>(.*?)</td>", re.S)

# Rótulo na tabela de estatísticas → chave no JSON. Rótulos de secção
# («Candidatos», «Colocados» a negrito) têm células vazias e são ignorados;
# os subtotais por sexo ficam de fora por não terem uso previsto no painel.
_METRICAS = {
    "Vagas": "vagas",
    "Candidatos": "candidatos",
    "em 1ª Opção": None,  # resolvido pelo contexto da secção (candidatos/colocados)
    "Colocados": "colocados",
    "Nota de Candidatura": "media_candidatura",
    "Provas de Ingresso": "media_provas",
    "Média do Secundário": "media_secundario",
    "Nota de Candidatura do Último Colocado pelo Contingente Geral": "nota_ultimo",
}


def _numero(texto: str) -> float | int | None:
    texto = texto.replace("&nbsp;", "").strip()
    if not texto:
        return None
    if "," in texto:
        return float(texto.replace(",", "."))
    return int(texto)


def parse_detalhe(html: str) -> dict:
    """Extrai a ficha completa de uma página detcursopi.asp."""
    cab = _CAB.search(html)
    if not cab:
        raise ValueError("página de detalhe sem cabeçalho")
    campos = {nome: regex.search(html) for nome, regex in _CAMPOS.items()}
    if not campos["grau"] or not campos["cnaef_par"] or not campos["tipo"]:
        raise ValueError("página de detalhe sem características")
    ficha: dict = {
        "curso": cab.group(1).strip(),
        "instituicao": cab.group(2).strip(),
        "grau": campos["grau"].group(1).strip(),
        "cnaef": campos["cnaef_par"].group(1),
        "cnaef_nome": campos["cnaef_par"].group(2).strip(),
        "duracao": campos["duracao"].group(1).strip() if campos["duracao"] else None,
        "ects": int(campos["ects"].group(1)) if campos["ects"] else None,
        "tipo_ensino": campos["tipo"].group(1).strip(),
        "concurso": campos["concurso"].group(1).strip() if campos["concurso"] else None,
        "vagas": int(campos["vagas"].group(1)) if campos["vagas"] else None,
    }
    minimos = _MINIMOS.search(html)
    if minimos:
        ficha["minimo_candidatura"] = int(minimos.group(1))
        ficha["minimo_provas"] = int(minimos.group(2))
    formula = _FORMULA.search(html)
    if formula:
        ficha["formula"] = _limpar(formula.group(1))
    provas = _PROVAS.search(html)
    if provas:
        ficha["provas_ingresso"] = _limpar(provas.group(1))

    anos = [int(a) for a in _ANOS.findall(html)]
    series: dict[str, dict] = {}
    seccao = None
    for rotulo_html, resto in _LINHA_STATS.findall(html):
        rotulo = re.sub(r"<[^>]+>|&nbsp;", "", rotulo_html).strip()
        if rotulo in ("Candidatos", "Colocados") and "<strong>" in rotulo_html:
            seccao = rotulo.lower()
            continue
        chave = _METRICAS.get(rotulo, "ausente")
        if chave == "ausente":
            continue
        if rotulo == "em 1ª Opção":
            chave = f"{seccao}_1opcao" if seccao else None
        elif rotulo in ("Candidatos", "Colocados"):
            chave = rotulo.lower()
        if chave is None:
            continue
        valores = [_numero(c) for c in _CELULA.findall(resto)]
        # 6 células: (ano1 f1, ano1 f2, ano2 f1, ano2 f2, ano3 f1, ano3 f2)
        if len(valores) != len(anos) * 2:
            continue
        for i, ano in enumerate(anos):
            for j, fase in enumerate((1, 2)):
                valor = valores[i * 2 + j]
                if valor is None:
                    continue
                series.setdefault(f"{ano}f{fase}", {})[chave] = valor
    ficha["series"] = series
    return ficha


def _limpar(html: str) -> str:
    texto = re.sub(r"<br\s*/?>", "\n", html)
    texto = re.sub(r"<[^>]+>", "", texto)
    texto = texto.replace("&nbsp;", " ")
    linhas = [" ".join(l.split()) for l in texto.splitlines()]
    return "\n".join(l for l in linhas if l)


def raspar(ano: int = ANO_GUIA, *, forcar: bool = False, limite: int | None = None) -> Path:
    dir_ano = common.DIR_BRUTO / "guias" / str(ano)
    pares: list[dict] = []
    for letra in string.ascii_uppercase:
        pagina = dir_ano / "indice" / f"{letra}.html"
        try:
            common.descarregar(f"{common.BASE_GUIAS}/indcurso.asp?letra={letra}", pagina, forcar=forcar)
        except RuntimeError:
            # Letras sem cursos (K, W, …) respondem 500 em vez de página vazia.
            print(f"  aviso: índice da letra {letra} indisponível")
            continue
        pares.extend(parse_indice(common.ler_html(pagina)))
    if len(pares) < 800:
        raise RuntimeError(f"só {len(pares)} pares no índice — o HTML do guia mudou?")

    if limite:
        pares = pares[:limite]
    fichas: dict[str, dict] = {}
    falhas: list[str] = []
    for n, par in enumerate(pares, 1):
        par_id = f"{par['code']}-{par['codc']}"
        pagina = dir_ano / "detalhe" / f"{par_id}.html"
        common.descarregar(
            f"{common.BASE_GUIAS}/detcursopi.asp?codc={par['codc']}&code={par['code']}",
            pagina,
            forcar=forcar,
        )
        try:
            fichas[par_id] = {"codc": par["codc"], "code": par["code"], **parse_detalhe(common.ler_html(pagina))}
        except ValueError:
            falhas.append(par_id)
        if n % 200 == 0:
            print(f"  {n}/{len(pares)} detalhes")
    if len(falhas) > len(pares) * 0.01:
        raise RuntimeError(f"{len(falhas)} páginas de detalhe sem parse ({falhas[:8]}…)")

    destino = dir_ano / "guia.json"
    destino.write_text(
        json.dumps(
            {"ano": ano, "pares": fichas, "falhas": falhas},
            ensure_ascii=False,
            indent=1,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"guia {ano}: {len(fichas)} pares ({len(falhas)} falhas) → {destino}")
    return destino


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ano", type=int, default=ANO_GUIA)
    parser.add_argument("--forcar", action="store_true")
    parser.add_argument("--limite", type=int, help="raspar só N pares (desenvolvimento)")
    args = parser.parse_args()
    try:
        raspar(args.ano, forcar=args.forcar, limite=args.limite)
    except RuntimeError as erro:
        sys.exit(f"erro: {erro}")


if __name__ == "__main__":
    main()
