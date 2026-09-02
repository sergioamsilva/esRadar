"""Parsing dos ficheiros de resultados por par, uma fixture por geração de
cabeçalho (1997-99, 2000-11, 2007, 2012-17, 2016 em prosa). Recortes reais dos
CSV convertidos dos XLS/ODS da DGES — ver reference/NOTAS.md."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import build  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def _ler(nome: str, ano: int, fase: int) -> dict[str, dict]:
    registos = build.ler_ficheiro_resultados(FIXTURES / nome, ano, fase)
    assert registos, f"{nome}: nada extraído"
    return {par: registo for par, registo, _nome in registos}


def test_1997_duas_linhas_de_cabecalho() -> None:
    """Candidatos, colocados em 1ª opção e médias só existem nestes anos."""
    r = _ler("cna97_1f_resultados.csv", 1997, 1)
    edu = r["0110-0182"]
    assert edu["vagas"] == 25 and edu["colocados"] == 25 and edu["sobras"] == 0
    assert edu["candidatos"] == 98 and edu["candidatos_1opcao"] == 15
    assert edu["colocados_1opcao"] == 11
    assert (edu["media_candidatura"], edu["media_provas"], edu["media_secundario"]) == (114.2, 100.1, 128.8)
    # Nota 0 = sem colocados pelo contingente geral → ausente, não zero.
    assert edu["nota_ultimo"] is None
    agr = r["0110-0198"]
    assert agr["nota_ultimo"] == 98.0 and agr["colocados"] == 13 and agr["sobras"] == 30
    nomes = {par: nome for par, _r, nome in build.ler_ficheiro_resultados(FIXTURES / "cna97_1f_resultados.csv", 1997, 1)}
    assert nomes["0110-0182"] == "Educadores de Infância"


def test_2000_codigo_estab_e_vaga_adicional() -> None:
    r = _ler("cna00_1f_resultados.csv", 2000, 1)
    amb = r["0110-0213"]
    assert amb == {"colocados": 14, "nota_ultimo": 112.1, "vagas": 30, "sobras": 16}
    assert r["0110-1039"]["nota_ultimo"] == 130.0


def test_2007_cabecalho_proprio_e_linhas_vazias() -> None:
    """2007: «Cód. Estab.», «Vagas 2007», «Candidatos 1ºop 2007», «Adicionais»;
    pares listados sem vagas não fazem série."""
    r = _ler("cna07_1f_resultados.csv", 2007, 1)
    assert "0110-0625" not in r, "linha vazia devia ser ignorada"
    vet = r["0110-1603"]
    assert vet["vagas"] == 12 and vet["candidatos_1opcao"] == 6 and vet["colocados"] == 12
    assert vet["nota_ultimo"] == 151.8 and vet["sobras"] == 0
    assert r["0110-9022"]["nota_ultimo"] is None and r["0110-9022"]["colocados"] == 1


def test_2013_terceira_fase_ods() -> None:
    """«Estudantes colocados», «Vagas criadas por recolocação», «Vagas não
    ocupadas na 3.ª fase», linha «(1)…(10)» sob o cabeçalho."""
    r = _ler("cna13_3f_resultados.csv", 2013, 3)
    farm = r["0110-8031"]
    assert farm == {"colocados": 0, "nota_ultimo": None, "vagas": 10, "vagas_recolocacao": 0, "sobras": 10}
    assert r["0110-8086"]["nota_ultimo"] == 145.8 and r["0110-8086"]["colocados"] == 1


def test_2016_segunda_fase_cabecalho_em_prosa() -> None:
    r = _ler("cna16_2f_resultados.csv", 2016, 2)
    vet = r["0140-8086"]
    assert vet["vagas"] == 2 and vet["vagas_recolocacao"] == 2
    assert vet["colocados"] == 4 and vet["nota_ultimo"] == 154.0 and vet["sobras"] == 0
    assert r["0140-L121"]["nota_ultimo"] == 105.5 and r["0140-L121"]["sobras"] == 15


def test_escala_das_notas() -> None:
    for nome, ano, fase in (
        ("cna97_1f_resultados.csv", 1997, 1),
        ("cna00_1f_resultados.csv", 2000, 1),
        ("cna07_1f_resultados.csv", 2007, 1),
        ("cna13_3f_resultados.csv", 2013, 3),
        ("cna16_2f_resultados.csv", 2016, 2),
    ):
        for registo in _ler(nome, ano, fase).values():
            nota = registo["nota_ultimo"]
            # O mínimo legal de 95 pontos só chega em 2000; em 1997 há cortes a 77.
            assert nota is None or 0 < nota <= 200, f"{nome}: nota {nota}"


def main() -> None:
    for nome, teste in sorted(globals().items()):
        if nome.startswith("test_"):
            teste()
            print(f"ok {nome}")


if __name__ == "__main__":
    main()
