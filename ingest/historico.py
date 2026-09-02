"""Série longa do CNA (1997-2017) a partir da página de estatísticas da DGES.

A página «Regime geral — Concurso Nacional de Acesso» aloja, de forma
estável, um ficheiro por ano e fase com os resultados por par
instituição/curso: vagas, colocados, nota do último colocado pelo
contingente geral e sobras. A 1ª fase existe desde 1997, a 2ª desde 2004 e
a 3ª desde 2012. Os três primeiros anos (1997-1999) trazem ainda candidatos
(total e em 1ª opção), colocados em 1ª opção e médias dos colocados.

De 2018 em diante os ficheiros são os mesmos que a época publica em
dges.gov.pt/coloc/{ano} — esses vêm por ingest.arquivo/ingest.coloc e não se
repetem aqui.

Cada ficheiro fica em data/raw/coloc/{ano}/fase{n}/ com o nome normalizado
cna{aa}_{f}f_resultados.{ext} (a extensão original: xls ou ods), a
proveniência em dges.json e a conversão para CSV ao lado. O formato do
cabeçalho muda várias vezes ao longo dos 21 anos — é o build que o mapeia,
por nome de coluna.

Uso: python -m ingest.historico [--anos 1997-2017]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json

from . import arquivo, common

PAGINA = f"{common.BASE_DGES}/pt/pagina/regime-geral-ensino-superior-publico-concurso-nacional-de-acesso"
_FICHEIROS = f"{common.BASE_DGES}/sites/default/files"
_ANTIGOS = f"{_FICHEIROS}/ficheiros_excel_acesso"

# (ano, fase) → URL, tal como ligados na página. Curado à mão: os nomes não
# seguem padrão nenhum entre 2004 e 2013.
FONTES: dict[tuple[int, int], str] = {
    **{(ano, 1): f"{_ANTIGOS}/fase1a{ano}.xls" for ano in range(1997, 2008)},
    **{(ano, 1): f"{_ANTIGOS}/fase1a{ano % 100:02d}.xls" for ano in range(2008, 2011)},
    (2011, 1): f"{_ANTIGOS}/cna2011_f1.xls",
    (2012, 1): f"{_ANTIGOS}/r_cna_12_1f1.xls",
    (2013, 1): f"{_ANTIGOS}/cna_13_1f_resultados_0.xls",
    **{(ano, 2): f"{_FICHEIROS}/fase2_{ano % 100:02d}.xls" for ano in range(2004, 2014)},
    (2012, 3): f"{_FICHEIROS}/fase3_12.xls",
    (2013, 3): f"{_ANTIGOS}/cna13_3f.ods",
    **{
        (ano, fase): f"{_ANTIGOS}/cna{ano % 100:02d}_{fase}f_resultados.xls"
        for ano in (2014, 2015)
        for fase in (1, 2, 3)
    },
    **{
        (ano, fase): f"{_FICHEIROS}/cna{ano % 100:02d}_{fase}f_resultados.ods"
        for ano in (2016, 2017)
        for fase in (1, 2, 3)
    },
}


def recuperar_ano(ano: int) -> None:
    for fase in (1, 2, 3):
        url = FONTES.get((ano, fase))
        if url is None:
            continue
        destino = common.DIR_BRUTO / "coloc" / str(ano) / f"fase{fase}"
        extensao = url.rsplit(".", 1)[-1]
        ficheiro = destino / f"cna{ano % 100:02d}_{fase}f_resultados.{extensao}"
        if common.descarregar(url, ficheiro):
            (destino / "dges.json").write_text(
                json.dumps(
                    {"origem": url, "pagina": PAGINA, "descarregado": dt.date.today().isoformat()},
                    ensure_ascii=False,
                    indent=1,
                )
                + "\n",
                encoding="utf-8",
            )
            print(f"  {ano} fase {fase}: descarregado")
        arquivo.converter_para_csv(ficheiro)


def recuperar(anos: range = range(1997, 2018)) -> None:
    for ano in anos:
        recuperar_ano(ano)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anos", default="1997-2017", help="intervalo, ex.: 1997-2017")
    args = parser.parse_args()
    inicio, _, fim = args.anos.partition("-")
    recuperar(range(int(inicio), int(fim or inicio) + 1))


if __name__ == "__main__":
    main()
