"""Manifesto SHA-256 de data/raw — deteta revisões silenciosas das fontes.

A DGES corrige estatísticas do guia sem qualquer aviso. Cada execução grava
um manifesto com o hash de todos os ficheiros brutos; o diff com o manifesto
anterior lista o que foi revisto, apareceu ou desapareceu.

Uso: python -m ingest.snapshot
"""

from __future__ import annotations

import hashlib
import json
from datetime import date

from . import common


def manifesto() -> dict[str, str]:
    hashes = {}
    for ficheiro in sorted(common.DIR_BRUTO.rglob("*")):
        if ficheiro.is_file():
            hashes[str(ficheiro.relative_to(common.DIR_BRUTO))] = hashlib.sha256(
                ficheiro.read_bytes()
            ).hexdigest()
    return hashes


def gravar() -> None:
    common.DIR_SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    atual = manifesto()
    anteriores = sorted(common.DIR_SNAPSHOTS.glob("*.json"))
    if anteriores:
        anterior = json.loads(anteriores[-1].read_text(encoding="utf-8"))
        revistos = [f for f in atual if f in anterior and anterior[f] != atual[f]]
        novos = [f for f in atual if f not in anterior]
        desaparecidos = [f for f in anterior if f not in atual]
        for rotulo, lista in (("revistos", revistos), ("novos", novos), ("desaparecidos", desaparecidos)):
            if lista:
                print(f"  {rotulo} ({len(lista)}): {', '.join(lista[:6])}{'…' if len(lista) > 6 else ''}")
    destino = common.DIR_SNAPSHOTS / f"{date.today().isoformat()}.json"
    destino.write_text(json.dumps(atual, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"snapshot: {len(atual)} ficheiros → {destino.name}")


if __name__ == "__main__":
    gravar()
