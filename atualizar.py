#!/usr/bin/env python3
"""Orquestrador do pipeline do esRadar. Ponto de entrada único.

Ordem fixa e explicada:
1. guias      — scraping do guia da candidatura (usa cache; --descarregar força)
2. coloc      — arquivo da época corrente (só com --fase N: os dados são
                efémeros e a fase tem de existir no site da DGES)
3. arquivo    — recuperação de épocas antigas via Arquivo.pt (idempotente,
                só descarrega o que falta)
3b. historico — série longa 1997-2017 da página de estatísticas da DGES
                (idempotente)
4. snapshot   — manifesto SHA-256 do raw, deteta revisões silenciosas
5. build      — junta tudo e escreve data/out (o contrato com o site)
6. testes     — falham alto antes de qualquer commit de dados

Uso: python atualizar.py [--descarregar] [--fase N] [--sem-testes]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def passo(nome: str, funcao) -> None:
    inicio = time.monotonic()
    print(f"— {nome}")
    funcao()
    print(f"  ({time.monotonic() - inicio:.1f}s)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descarregar", action="store_true", help="ignora a cache do guia")
    parser.add_argument("--fase", type=int, choices=(1, 2, 3), help="arquiva esta fase da época corrente")
    parser.add_argument("--sem-testes", action="store_true")
    args = parser.parse_args()

    from ingest import arquivo, build, coloc, guias, historico, infocursos, snapshot

    passo("guia da candidatura", lambda: guias.raspar(forcar=args.descarregar))
    if args.fase:
        passo(f"época corrente, fase {args.fase}", lambda: coloc.arquivar_fase(coloc.ANO_CORRENTE, args.fase))
    passo("histórico via Arquivo.pt", lambda: [arquivo.recuperar_ano(a) for a in range(2018, 2026)])
    passo("série longa 1997-2017 (DGES)", historico.recuperar)
    passo("infocursos", lambda: infocursos.atualizar(forcar=args.descarregar))
    passo("snapshot", snapshot.gravar)
    passo("build", build.construir)
    if not args.sem_testes:
        passo(
            "testes",
            lambda: [
                subprocess.run([sys.executable, str(t)], check=True)
                for t in sorted((RAIZ / "tests").glob("test_*.py"))
            ],
        )
    print("concluído")


if __name__ == "__main__":
    main()
