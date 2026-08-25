"""Semeia sugestões de crosswalk para pares que mudaram de código.

Compara o universo de pares do primeiro e do último ano dos resultados:
um par que desapareceu e outro que apareceu com o MESMO nome de curso
normalizado no MESMO estabelecimento é provavelmente uma recodificação.
As sugestões vão para reference/pares_sugestoes.yaml — a decisão de as
promover a reference/pares.yaml é sempre humana; nada é fundido
automaticamente (ver CLAUDE.md).

Uso: python -m ingest.semear
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import yaml

from . import build, common


def universo(ano: int) -> dict[str, tuple[str, str]]:
    """{par: (nome_curso, code)} do primeiro ficheiro de fase 1 desse ano."""
    caminho = next(common.DIR_BRUTO.glob(f"coloc/{ano}/fase1/cna*_resultados.csv"))
    pares = {}
    with caminho.open(encoding="utf-8") as f:
        linhas = list(csv.reader(f))
    cab = next(l for l in linhas if any("Código Instit." in c for c in l))
    idx = {" ".join(c.split()): i for i, c in enumerate(cab) if c.strip()}
    for linha in linhas:
        if len(linha) <= idx["Nome do Curso"]:
            continue
        code, codc = linha[idx["Código Instit."]].strip(), linha[idx["Código Curso"]].strip()
        if len(code) == 4 and code.isdigit() and codc:
            pares[f"{code}-{codc}"] = (linha[idx["Nome do Curso"]].strip(), code)
    return pares


def semear(ano_antigo: int = 2018, ano_novo: int = 2026) -> Path:
    antigos = universo(ano_antigo)
    novos = universo(ano_novo)

    desaparecidos = {p: v for p, v in antigos.items() if p not in novos}
    aparecidos = {p: v for p, v in novos.items() if p not in antigos}

    por_chave: dict[tuple[str, str], list[str]] = defaultdict(list)
    for par, (nome, code) in aparecidos.items():
        por_chave[(common.normalizar(nome), code)].append(par)

    sugestoes = []
    for par, (nome, code) in sorted(desaparecidos.items()):
        candidatos = por_chave.get((common.normalizar(nome), code), [])
        if len(candidatos) == 1:
            sugestoes.append(
                {
                    "de": par,
                    "para": candidatos[0],
                    "curso": nome,
                    "motivo": f"mesmo nome normalizado no mesmo estabelecimento ({ano_antigo}→{ano_novo})",
                }
            )

    destino = common.DIR_REFERENCIA / "pares_sugestoes.yaml"
    destino.write_text(
        yaml.safe_dump(
            {
                "nota": "SUGESTÕES do semeador — rever uma a uma e promover a pares.yaml à mão. "
                "Nunca usar diretamente no build.",
                "sugestoes": sugestoes,
            },
            allow_unicode=True,
            sort_keys=False,
            width=110,
        ),
        encoding="utf-8",
    )
    print(
        f"semear: {len(desaparecidos)} pares desapareceram desde {ano_antigo}, "
        f"{len(sugestoes)} recodificações prováveis → {destino.name}"
    )
    return destino


if __name__ == "__main__":
    semear()
