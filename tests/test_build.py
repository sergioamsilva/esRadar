"""Coerência interna de data/out depois do build."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import common  # noqa: E402

SAIDA = common.DIR_SAIDA


def _ler(nome: str) -> dict:
    return json.loads((SAIDA / nome).read_text(encoding="utf-8"))


def test_universo() -> None:
    cursos = _ler("cursos.json")["cursos"]
    assert len(cursos) > 1000, f"só {len(cursos)} pares ativos"
    fichas = list((SAIDA / "par").glob("*.json"))
    assert len(fichas) >= len(cursos), "há pares ativos sem ficha"


def test_somas_batem() -> None:
    """As somas do índice têm de bater com os agregados por instituição."""
    cursos = _ler("cursos.json")["cursos"]
    instituicoes = _ler("instituicoes.json")["instituicoes"]
    assert sum(c["vagas"] or 0 for c in cursos) == sum(i["vagas"] for i in instituicoes)
    assert sum(c["colocados_2026f1"] or 0 for c in cursos) == sum(
        i["colocados_f1"] for i in instituicoes
    )


def test_notas_na_escala() -> None:
    for ficha in (SAIDA / "par").glob("*.json"):
        dados = json.loads(ficha.read_text(encoding="utf-8"))
        for chave, registo in dados["series"].items():
            nota = registo.get("nota_ultimo")
            assert nota is None or 0 <= nota <= 200, f"{ficha.name} {chave}: nota {nota}"


def test_encoding() -> None:
    """Acentuação intacta: uma vítima típica do windows-1252 mal descodificado."""
    cursos = _ler("cursos.json")["cursos"]
    assert any("ç" in (c["curso"] or "") for c in cursos), "nenhum curso com ç — encoding?"
    assert not any("Ã§" in (c["curso"] or "") for c in cursos), "mojibake detetado"


def test_composicoes_somam_100() -> None:
    """As composições do Infocursos têm de somar ~100% — apanha erros de
    escala (frações vs percentagens) e linhas suprimidas na fonte."""
    for ficha in (SAIDA / "par").glob("*.json"):
        d = json.loads(ficha.read_text(encoding="utf-8"))
        info = d.get("infocursos") or {}
        for bloco, cols in (
            ("formas_ingresso", ("cna_1opcao", "cna_outras", "concurso_local", "mudanca_curso", "maiores_23", "outros")),
            ("apos_1_ano", ("fica", "muda_curso", "muda_estabelecimento", "fora")),
        ):
            b = info.get(bloco)
            if b:
                soma = sum(b[c] for c in cols)
                assert 60 <= soma <= 130, f"{ficha.name} {bloco}: soma {soma}"


def test_epoca() -> None:
    epoca = _ler("epoca.json")
    assert epoca["ano"] == 2026
    assert 1 in epoca["fases_arquivadas"]


def main() -> None:
    for nome, teste in sorted(globals().items()):
        if nome.startswith("test_"):
            teste()
            print(f"ok {nome}")


if __name__ == "__main__":
    main()
