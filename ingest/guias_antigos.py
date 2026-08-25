"""Recupera edições antigas do guia da DGES a partir do Arquivo.pt.

Cada edição do guia (o site é reescrito todos os anos no mesmo URL) traz as
estatísticas dos três anos anteriores — candidatos por sexo e 1ª opção,
médias dos colocados — que mais nenhuma fonte estruturada tem. Com as
edições de 2020 e 2023 mais o guia corrente, a série de procura por curso
recua até 2017.

Uma captura pertence à edição Y se foi feita entre julho de Y e abril de
Y+1 (o guia sai em julho). O HTML é idêntico ao atual e o parser de
ingest/guias.py aplica-se tal e qual.

Uso: python -m ingest.guias_antigos --edicao 2023 [--limite N]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path

from . import common, guias

CDX = "https://arquivo.pt/wayback/cdx"
REPLAY = "https://arquivo.pt/noFrame/replay"


def capturas_da_edicao(edicao: int) -> dict[str, tuple[str, str]]:
    """{par: (timestamp, url_original)} — a captura mais recente da edição."""
    resp = common.sessao().get(
        CDX,
        params={
            "url": "dges.gov.pt/guias/detcursopi.asp*",
            "output": "json",
            "filter": "statuscode:200",
            "from": f"{edicao}0701000000",
            "to": f"{edicao + 1}0430235959",
        },
        timeout=300,
    )
    resp.raise_for_status()
    melhores: dict[str, tuple[str, str]] = {}
    for linha in resp.text.splitlines():
        if not linha.strip():
            continue
        captura = json.loads(linha)
        query = urllib.parse.urlparse(captura["url"]).query
        params = dict(urllib.parse.parse_qsl(query.lower()))
        codc, code = params.get("codc", "").upper(), params.get("code", "")
        if not re.fullmatch(r"[A-Z0-9]\d{3}", codc) or not re.fullmatch(r"\d{4}", code):
            continue
        par = f"{code}-{codc}"
        if par not in melhores or captura["timestamp"] > melhores[par][0]:
            melhores[par] = (captura["timestamp"], captura["url"])
    return melhores


def recuperar(edicao: int, *, limite: int | None = None) -> Path:
    dir_edicao = common.DIR_BRUTO / "guias" / str(edicao)
    capturas = capturas_da_edicao(edicao)
    print(f"edição {edicao}: {len(capturas)} pares com captura no Arquivo.pt")
    itens = sorted(capturas.items())[:limite] if limite else sorted(capturas.items())

    fichas: dict[str, dict] = {}
    falhas: list[str] = []
    for n, (par, (timestamp, url)) in enumerate(itens, 1):
        pagina = dir_edicao / "detalhe" / f"{par}.html"
        try:
            common.descarregar(f"{REPLAY}/{timestamp}id_/{url}", pagina)
        except RuntimeError:
            falhas.append(par)
            continue
        try:
            code, codc = par.split("-", 1)
            fichas[par] = {"codc": codc, "code": code, **guias.parse_detalhe(common.ler_html(pagina))}
        except ValueError:
            falhas.append(par)
        if n % 200 == 0:
            print(f"  {n}/{len(itens)}")

    destino = dir_edicao / "guia.json"
    destino.write_text(
        json.dumps(
            {"ano": edicao, "origem": "arquivo.pt", "pares": fichas, "falhas": falhas},
            ensure_ascii=False,
            indent=1,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"edição {edicao}: {len(fichas)} pares extraídos ({len(falhas)} falhas) → {destino}")
    return destino


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edicao", type=int, required=True)
    parser.add_argument("--limite", type=int)
    args = parser.parse_args()
    try:
        recuperar(args.edicao, limite=args.limite)
    except RuntimeError as erro:
        sys.exit(f"erro: {erro}")


if __name__ == "__main__":
    main()
