"""Parsing das páginas da época de colocações, sobre HTML real congelado."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import coloc  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def test_ultimos_colocados() -> None:
    html = (FIXTURES / "col1listamin_0300.html").read_bytes().decode("windows-1252")
    registos = coloc.parse_ultimos(html)
    assert len(registos) > 30, f"só {len(registos)} cursos na Universidade de Aveiro"
    adm = next(r for r in registos if r["codc"] == "9002")
    assert adm["curso"] == "Administração Pública"
    assert adm["grau"] == "Licenciatura - 1º ciclo"
    assert adm["nota_ultimo"] == 145.5
    # Nenhuma nota fora da escala 0-200 do concurso.
    assert all(0 <= r["nota_ultimo"] <= 200 for r in registos)


def main() -> None:
    for nome, teste in sorted(globals().items()):
        if nome.startswith("test_"):
            teste()
            print(f"ok {nome}")


if __name__ == "__main__":
    main()
