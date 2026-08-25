"""Recupera do Arquivo.pt os resultados de épocas que a DGES já retirou.

A DGES apaga dges.gov.pt/coloc/{ano} no fim de cada época (404 fora de
época), mas o Arquivo.pt preservou os ficheiros cna{aa}_{f}f_resultados.xls
de 2018 a 2025 — um por fase, com todos os pares instituição/curso: vagas,
colocados, nota do último colocado pelo contingente geral e sobras.

Cada download fica em data/raw/coloc/{ano}/fase{n}/ com a proveniência
(timestamp do Arquivo.pt) em arquivo_pt.json. Depois converte para CSV
(LibreOffice headless) para que o build não dependa do formato .xls.

Uso: python -m ingest.arquivo [--anos 2018-2025]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import common

CDX = "https://arquivo.pt/wayback/cdx"
REPLAY = "https://arquivo.pt/noFrame/replay"


def snapshot_mais_recente(url: str) -> tuple[str, str] | None:
    """Devolve (timestamp, digest) da captura 200 mais recente de `url`."""
    resp = common.sessao().get(
        CDX,
        params={"url": url, "output": "json", "filter": "statuscode:200"},
        timeout=common.TEMPO_LIMITE,
    )
    resp.raise_for_status()
    capturas = [json.loads(linha) for linha in resp.text.splitlines() if linha.strip()]
    if not capturas:
        return None
    ultima = max(capturas, key=lambda c: c["timestamp"])
    return ultima["timestamp"], ultima.get("digest", "")


def converter_para_csv(xls: Path) -> Path | None:
    """Converte um .xls para .csv ao lado, via LibreOffice. None se indisponível."""
    csv = xls.with_suffix(".csv")
    if csv.exists():
        return csv
    if shutil.which("libreoffice") is None:
        print(f"  aviso: libreoffice indisponível, {xls.name} fica por converter")
        return None
    # --convert-to escreve no --outdir com o mesmo nome base; usar um diretório
    # temporário evita colisões com instâncias concorrentes do LibreOffice.
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "csv", "--outdir", tmp, str(xls)],
            check=True,
            capture_output=True,
            timeout=120,
        )
        shutil.move(Path(tmp) / csv.name, csv)
    return csv


def recuperar_ano(ano: int) -> None:
    aa = ano % 100
    for fase in (1, 2, 3):
        destino = common.DIR_BRUTO / "coloc" / str(ano) / f"fase{fase}"
        xls = destino / f"cna{aa:02d}_{fase}f_resultados.xls"
        url = f"https://dges.gov.pt/coloc/{ano}/cna{aa:02d}_{fase}f_resultados.xls"
        if not xls.exists():
            captura = snapshot_mais_recente(url)
            if captura is None:
                print(f"  {ano} fase {fase}: sem captura no Arquivo.pt")
                continue
            timestamp, digest = captura
            common.descarregar(f"{REPLAY}/{timestamp}id_/{url}", xls)
            (destino / "arquivo_pt.json").write_text(
                json.dumps(
                    {"origem": url, "timestamp_arquivo_pt": timestamp, "digest": digest},
                    ensure_ascii=False,
                    indent=1,
                )
                + "\n",
                encoding="utf-8",
            )
            print(f"  {ano} fase {fase}: recuperado (captura {timestamp})")
        converter_para_csv(xls)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anos", default="2018-2025", help="intervalo, ex.: 2018-2025")
    args = parser.parse_args()
    inicio, _, fim = args.anos.partition("-")
    anos = range(int(inicio), int(fim or inicio) + 1)
    for ano in anos:
        print(f"{ano}:")
        recuperar_ano(ano)
    # A época corrente foi arquivada diretamente da DGES; só falta converter.
    for xls in sorted((common.DIR_BRUTO / "coloc").glob("*/fase*/cna*_resultados.xls")):
        converter_para_csv(xls)


if __name__ == "__main__":
    main()
