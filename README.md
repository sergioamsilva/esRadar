# esRadar

Dashboard das colocações no ensino superior público português — Concurso
Nacional de Acesso (CNA/DGES). Notas do último colocado, vagas, colocados e
procura por par instituição/curso, de 2018 a 2026.

## Arquitetura

Pipeline Python (3 dependências: `duckdb`, `pyyaml`, `requests`) que arquiva
as fontes em `data/raw/` (versionado — os dados da DGES são pequenos e
efémeros), constrói `data/out/` (o contrato com o site, revisto por humanos
via `git diff`) e um site estático Astro em `site/`.

```
python atualizar.py                # pipeline completo com cache
python atualizar.py --fase 2      # + arquiva a fase 2 da época corrente
python -m ingest.coloc --fase 2   # só o arquivo da época (urgente no dia)
```

## Fontes

- **DGES — resultados do CNA por fase** (`dges.gov.pt/coloc/{ano}`): efémeros,
  arquivados no próprio dia; 2018–2025 recuperados do [Arquivo.pt](https://arquivo.pt).
- **DGES — guia da candidatura** (`dges.gov.pt/guias`): metadados dos pares e
  estatísticas dos 3 anos anteriores, incluindo candidatos em 1ª opção.
- **Infocursos (MECI)**: bases anuais 2015–2026 (por integrar).

Peculiaridades documentadas em `reference/NOTAS.md`.

## Privacidade

As listas nominais de colocados/candidatos **não são arquivadas** — só dados
agregados por par instituição/curso.

## Calendário da época

A DGES retira as páginas no fim da época. Arquivar no dia:
- 1ª fase: fim de agosto ✔ (arquivada 2026-08-25)
- 2ª fase: meados de setembro — `python atualizar.py --fase 2`
- 3ª fase: início de outubro — `python atualizar.py --fase 3`
