"""Parsing do guia da DGES sobre HTML real congelado em fixtures/."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import guias  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def ler(nome: str) -> str:
    return (FIXTURES / nome).read_bytes().decode("windows-1252")


def test_indice() -> None:
    pares = guias.parse_indice(ler("indcurso_E.html"))
    assert len(pares) > 300, f"só {len(pares)} pares na letra E"
    economia = [p for p in pares if p["codc"] == "9081" and p["code"] == "6800"]
    assert economia == [
        {
            "codc": "9081",
            "curso": "Economia",
            "grau": "Lic-1º cic",
            "code": "6800",
            "instituicao": "ISCTE - Instituto Universitário de Lisboa",
            "vagas": 72,
        }
    ]
    # Encoding: nomes com acentuação têm de sobreviver ao windows-1252.
    assert any("Évora" in p["instituicao"] for p in pares)


def test_detalhe_iscte() -> None:
    ficha = guias.parse_detalhe(ler("detcursopi_6800_9081.html"))
    assert ficha["curso"] == "Economia"
    assert ficha["instituicao"] == "ISCTE - Instituto Universitário de Lisboa"
    assert ficha["vagas"] == 72
    assert ficha["cnaef"] == "314"
    assert ficha["minimo_candidatura"] == 100
    assert "Matemática A" in ficha["provas_ingresso"]
    s = ficha["series"]
    assert s["2025f1"]["nota_ultimo"] == 162.0
    assert s["2025f1"]["candidatos"] == 941
    assert s["2025f1"]["candidatos_1opcao"] == 77
    assert s["2024f2"]["colocados"] == 15
    assert s["2023f1"]["media_secundario"] == 171.1
    # Desagregação por sexo, nas duas secções.
    assert s["2025f1"]["candidatos_mulheres"] == 427
    assert s["2025f1"]["candidatos_homens"] == 514
    assert s["2025f1"]["colocados_mulheres"] == 36
    assert s["2025f1"]["colocados_homens"] == 36


def test_detalhe_acores() -> None:
    # Curso pequeno dos Açores: código de curso alfanumérico (L344) e séries
    # possivelmente incompletas — o parser não pode inventar valores.
    ficha = guias.parse_detalhe(ler("detcursopi_0140_L344.html"))
    assert ficha["instituicao"].startswith("Universidade dos Açores")
    for chave, valores in ficha["series"].items():
        assert set(valores) <= {
            "vagas",
            "candidatos",
            "candidatos_1opcao",
            "candidatos_mulheres",
            "candidatos_homens",
            "colocados",
            "colocados_1opcao",
            "colocados_mulheres",
            "colocados_homens",
            "media_candidatura",
            "media_provas",
            "media_secundario",
            "nota_ultimo",
        }, f"{chave}: {valores}"


def main() -> None:
    for nome, teste in sorted(globals().items()):
        if nome.startswith("test_"):
            teste()
            print(f"ok {nome}")


if __name__ == "__main__":
    main()
