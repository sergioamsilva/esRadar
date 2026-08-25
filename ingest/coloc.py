"""Arquivador da época de colocações do CNA (dges.gov.pt/coloc/{ano}).

Estas páginas são efémeras: no fim da época a DGES retira-as e os anos
anteriores passam a responder 404. Arquivar primeiro, interpretar depois —
o HTML bruto fica versionado em data/raw/coloc/{ano}/fase{n}/ e qualquer
correção de parsing é retroativa, sem novo scraping.

Por decisão do projeto NÃO se arquivam as listas nominais de colocados nem
as listas ordenadas de candidatos: contêm nomes de estudantes. Só dados
agregados por par instituição/curso.

Uso: python -m ingest.coloc --ano 2026 --fase 1 [--forcar]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

from . import common

ANO_CORRENTE = 2026

# CodR distingue os dois subsistemas públicos no site das colocações.
SUBSISTEMAS = {"11": "universitario", "12": "politecnico"}


def _base(ano: int) -> str:
    return f"{common.BASE_DGES}/coloc/{ano}"


def _dir_fase(ano: int, fase: int) -> Path:
    return common.DIR_BRUTO / "coloc" / str(ano) / f"fase{fase}"


class _Tabelas(HTMLParser):
    """Extrai o texto das células (<td>) agrupado por linha (<tr>)."""

    def __init__(self) -> None:
        super().__init__()
        self.linhas: list[list[str]] = []
        self._linha: list[str] | None = None
        self._celula: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "tr":
            self._linha = []
        elif tag == "td" and self._linha is not None:
            self._celula = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._celula is not None and self._linha is not None:
            self._linha.append(" ".join("".join(self._celula).split()))
            self._celula = None
        elif tag == "tr" and self._linha is not None:
            if self._linha:
                self.linhas.append(self._linha)
            self._linha = None

    def handle_data(self, data: str) -> None:
        if self._celula is not None:
            self._celula.append(data)


def linhas_de_tabela(html: str) -> list[list[str]]:
    parser = _Tabelas()
    parser.feed(html)
    return parser.linhas


_OPCAO = re.compile(r"<option value='(\d{4})'[^>]*>\s*\d{4} - ([^<]+)")


def estabelecimentos(html: str) -> list[tuple[str, str]]:
    """Pares (código, nome) do <select> de estabelecimentos."""
    return [(cod, nome.strip()) for cod, nome in _OPCAO.findall(html)]


_NOTA = re.compile(r"^\d{1,3},\d$|^\d{1,3}$")


def parse_ultimos(html: str) -> list[dict]:
    """Linhas [codc, curso, grau, nota] da página col{n}listamin.asp."""
    registos = []
    for linha in linhas_de_tabela(html):
        if len(linha) != 4:
            continue
        codc, curso, grau, nota = (c.strip() for c in linha)
        if not re.match(r"^[A-Z0-9]\d{3}$", codc) or not _NOTA.match(nota):
            continue
        registos.append(
            {
                "codc": codc,
                "curso": curso,
                "grau": grau,
                "nota_ultimo": float(nota.replace(",", ".")),
            }
        )
    return registos


def arquivar_fase(ano: int, fase: int, *, forcar: bool = False) -> Path:
    base = _base(ano)
    destino = _dir_fase(ano, fase)
    destino.mkdir(parents=True, exist_ok=True)
    novos = 0

    # 1. Índice da época e documentos aí ligados (notas, resultados PDF/XLS).
    indice = destino / "index.html"
    novos += common.descarregar(f"{base}/", indice, forcar=forcar)
    html_indice = common.ler_html(indice)
    for href in re.findall(r'href="([^"]+\.(?:pdf|xls[xm]?))"', html_indice, re.I):
        if href.startswith("http"):
            url, nome = href, href.rsplit("/", 1)[-1]
        else:
            url, nome = f"{base}/{href}", href.rsplit("/", 1)[-1]
        novos += common.descarregar(url, destino / nome, forcar=forcar)

    # 2. Estabelecimentos por subsistema e, para cada um, as duas páginas
    #    agregadas: últimos colocados e últimos colocados por etapa.
    estabs: dict[str, dict] = {}
    for codr, subsistema in SUBSISTEMAS.items():
        pagina = destino / f"estabs_{codr}.html"
        novos += common.descarregar(
            f"{base}/col{fase}listas.asp?CodR={codr}&action=2", pagina, forcar=forcar
        )
        pares = estabelecimentos(common.ler_html(pagina))
        if not pares:
            raise RuntimeError(
                f"nenhum estabelecimento no subsistema {subsistema} — "
                f"a fase {fase} ainda não saiu, ou o HTML mudou"
            )
        for cod, nome in pares:
            estabs[cod] = {"nome": nome, "codr": codr, "subsistema": subsistema}
            for pagina_asp, pasta in (("listamin", "min"), ("listamintp", "mintp")):
                novos += common.descarregar(
                    f"{base}/col{fase}{pagina_asp}.asp?CodR={codr}&CodEstab={cod}",
                    destino / pasta / f"{cod}.html",
                    forcar=forcar,
                )

    # O XLS de resultados é a fonte central do build — converter já para CSV.
    from . import arquivo

    for xls in destino.glob("cna*_resultados.xls"):
        arquivo.converter_para_csv(xls)

    # 3. Vagas sobrantes (agregadas por subsistema).
    novos += common.descarregar(f"{base}/col{fase}sobras.asp", destino / "sobras.html", forcar=forcar)
    for codr in SUBSISTEMAS:
        novos += common.descarregar(
            f"{base}/col{fase}sobrasres.asp?CodR={codr}",
            destino / f"sobras_{codr}.html",
            forcar=forcar,
        )

    # 4. Extração: notas do último colocado por par, a partir das páginas min.
    registos = []
    sem_dados = []
    for cod, meta in sorted(estabs.items()):
        pagina = destino / "min" / f"{cod}.html"
        cursos = parse_ultimos(common.ler_html(pagina))
        if not cursos:
            sem_dados.append(cod)
        for curso in cursos:
            registos.append({"code": cod, "estabelecimento": meta["nome"], "subsistema": meta["subsistema"], **curso})
    if len(sem_dados) > len(estabs) * 0.05:
        raise RuntimeError(
            f"{len(sem_dados)} de {len(estabs)} estabelecimentos sem cursos extraídos "
            f"({', '.join(sem_dados[:8])}…) — o HTML terá mudado"
        )
    (destino / "listas.json").write_text(
        json.dumps(
            {"ano": ano, "fase": fase, "estabelecimentos": estabs, "ultimos_colocados": registos},
            ensure_ascii=False,
            indent=1,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"coloc {ano} fase {fase}: {len(estabs)} estabelecimentos, "
        f"{len(registos)} pares com nota, {novos} ficheiros novos → {destino}"
    )
    return destino


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ano", type=int, default=ANO_CORRENTE)
    parser.add_argument("--fase", type=int, required=True, choices=(1, 2, 3))
    parser.add_argument("--forcar", action="store_true", help="re-descarrega mesmo com cache")
    args = parser.parse_args()
    try:
        arquivar_fase(args.ano, args.fase, forcar=args.forcar)
    except RuntimeError as erro:
        sys.exit(f"erro: {erro}")


if __name__ == "__main__":
    main()
