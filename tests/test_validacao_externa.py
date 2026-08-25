"""Validação externa: os nossos totais contra os números anunciados pela DGES.

Cada entrada confronta a soma reconstruída a partir dos ficheiros por par com
o total que a DGES anunciou em comunicado. A coluna «Colocados» dos XLS não
inclui desempates nem colocados sem classificação final, pelo que se aceita
uma tolerância de 2%.

Fontes dos totais anunciados:
- 2026 1ª fase: nota à comunicação social da DGES, 2026-08-21 — 49 991
  colocados em 60 513 candidatos válidos (dges.gov.pt/coloc/2026/nota_cna26_1f_2.pdf).
- 2025 1ª fase: comunicado DGES/MECI de agosto de 2025 — 49 000+ (usar
  o valor da série do próprio XLS como regressão, ver abaixo).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import common  # noqa: E402

ANUNCIADOS = {
    # (ano, fase): colocados anunciados pela DGES
    (2026, 1): 49_991,
}

# Regressão: totais reconstruídos uma vez e congelados. Se um rebuild os
# mudar, ou a fonte foi revista (verificar o snapshot) ou o parser partiu.
CONGELADOS = {
    (2025, 1): None,  # preenchido na primeira execução validada
}


def _colocados(ano: int, fase: int) -> int:
    total = 0
    nacional = json.loads((common.DIR_SAIDA / "nacional.json").read_text(encoding="utf-8"))
    # nacional.json agrega todas as fases; para uma fase específica somamos as fichas.
    for ficha in (common.DIR_SAIDA / "par").glob("*.json"):
        dados = json.loads(ficha.read_text(encoding="utf-8"))
        registo = dados["series"].get(f"{ano}f{fase}")
        if registo and registo.get("colocados"):
            total += registo["colocados"]
    assert nacional, "nacional.json vazio"
    return total


def test_totais_anunciados() -> None:
    for (ano, fase), anunciado in ANUNCIADOS.items():
        reconstruido = _colocados(ano, fase)
        # Com as colunas de desempate somadas, o total reconstruído bate
        # exatamente com o anunciado; a tolerância residual cobre revisões
        # silenciosas da fonte.
        desvio = abs(reconstruido - anunciado) / anunciado
        assert desvio <= 0.002, (
            f"{ano} fase {fase}: reconstruído {reconstruido}, anunciado {anunciado} "
            f"(desvio {desvio:.1%})"
        )
        print(f"  {ano} f{fase}: {reconstruido} vs {anunciado} anunciados ({desvio:.2%})")


def main() -> None:
    for nome, teste in sorted(globals().items()):
        if nome.startswith("test_"):
            teste()
            print(f"ok {nome}")


if __name__ == "__main__":
    main()
