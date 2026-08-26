# esRadar — regras para agentes

Dashboard das colocações no ensino superior público (CNA/DGES). Arquitetura
decalcada do snsRadar: pipeline Python → `data/out` versionado (contrato) →
site Astro estático. Ler `reference/NOTAS.md` antes de tocar em parsers.

## Regras duras

- **Nunca usar `resp.text`** nas páginas da DGES — sempre
  `content.decode("windows-1252")` (`common.ler_html`).
- **Rate-limit de 1 pedido/segundo** ao site da DGES (`common.descarregar`).
  Nunca contornar.
- **Não arquivar listas nominais** de candidatos/colocados — têm nomes de
  estudantes. Só agregados por par instituição/curso.
- Os dados da época em `dges.gov.pt/coloc/{ano}` são **efémeros**: quando uma
  fase sai (2ª: setembro; 3ª: outubro), `python atualizar.py --fase N` e
  commit do raw **no próprio dia**.
- `data/raw` e `data/out` são versionados. O workflow de publicação nunca
  corre o pipeline — os dados entram por commit revisto.
- JSON de saída determinístico: chaves ordenadas, uma casa decimal nas notas.
- Parsers falham alto (>1% de páginas sem a estrutura esperada = abortar),
  e só se alteram com fixtures reais em `tests/fixtures/`.
- Crosswalk (`reference/*.yaml`) é curado à mão: um par que desaparece gera
  aviso, nunca fusão automática.

## Comandos

```
.venv/bin/python atualizar.py            # pipeline completo (usa cache)
.venv/bin/python atualizar.py --fase 2   # + arquiva a fase 2 da época
.venv/bin/python tests/test_*.py         # testes são scripts, sem pytest
cd site && npm run build                 # site (lê ../data/out)
```

## Antes de dar por terminado

1. Pipeline completo sem erros + testes verdes.
2. `npm run build` gera ≥1000 fichas de curso.
3. Nas páginas alteradas: verificar a 390 px e em ecrã largo, nos dois temas,
   e que o conteúdo é legível sem JavaScript.
