# esRadar

**As colocações no ensino superior público, curso a curso — 2018 a 2026.**

Todos os anos, no fim de agosto, a DGES publica os resultados do Concurso
Nacional de Acesso. E todos os anos, uns meses depois, apaga-os: as páginas
de `dges.gov.pt/coloc/2025` respondem hoje 404, como as de 2024, como as de
todos os anos anteriores. A memória do acesso ao ensino superior português
vive em PDFs dispersos e em capturas de ecrã de jornais.

O esRadar existe para resolver isso. Arquiva os resultados de cada fase no
próprio dia em que saem, recuperou do [Arquivo.pt](https://arquivo.pt) tudo
o que a DGES já tinha apagado (2018–2025, incluindo edições antigas do guia
de candidatura), cruza-os com o [Infocursos](https://infocursos.medu.pt) do
MECI, e publica tudo num sítio estático onde cada número é verificável até
ao ficheiro fonte.

O resultado: 1170 cursos com nota de corte, procura, vagas, sobras,
contingentes especiais, demografia, permanência e desemprego dos diplomados
— e as perguntas respondidas que mais ninguém responde, como «esperar pela
2.ª fase compensa?» (spoiler: em 66% dos casos a nota *sobe*).

## Como funciona

Duas metades, deliberadamente separadas:

```
python atualizar.py            # pipeline completo (usa cache local)
python atualizar.py --fase 2   # + arquiva a fase 2 da época corrente
cd site && npm run build       # o sítio, gerado a partir de data/out
```

O pipeline Python (só `duckdb`, `pyyaml` e `requests`) escreve JSON
determinístico em `data/out/` — que fica versionado no git, para que
qualquer alteração aos números seja revisível num diff antes de publicar. O
sítio (Astro, sem frameworks de UI, gráficos todos em SVG desenhado à mão)
lê esses ficheiros em build e nunca corre o pipeline: o que está no ar é o
que foi commitado e revisto.

Os dados brutos também estão versionados, com a proveniência anotada — os
ficheiros recuperados do Arquivo.pt trazem ao lado o timestamp da captura
de onde vieram. As peculiaridades das fontes (o windows-1252 dos ASP da
DGES, os cabeçalhos que mudam entre fases, as letras do índice que
respondem 500) estão documentadas em `reference/NOTAS.md`, porque da
próxima vez que algo partir foi provavelmente uma delas.

## O que não encontras aqui

- **Listas nominais.** A DGES publica os nomes dos colocados durante a
  época; este projeto não os arquiva nem reproduz. Só agregados por par
  curso/instituição.
- **Rankings de qualidade.** A nota do último colocado mede o equilíbrio
  entre procura e vagas — não a qualidade do curso. O sítio repete este
  aviso em todo o lado, de propósito.
- **Dados anteriores a 2018.** Antes disso só há PDFs e portais extintos;
  preferimos uma série curta e verificável a uma longa e remendada.

## Calendário

A DGES retira as páginas no fim de cada época — arquivar no dia é a única
garantia:

- 1.ª fase: fim de agosto ✔ (2026 arquivada a 25-08)
- 2.ª fase: meados de setembro — `python atualizar.py --fase 2`
- 3.ª fase: início de outubro — `python atualizar.py --fase 3`

O `scripts/atualizacao_agendada.sh` faz isto por cron durante a janela da
época.

## Fontes

Resultados por fase e guia da candidatura da
[DGES](https://www.dges.gov.pt); histórico via
[Arquivo.pt](https://arquivo.pt); estatísticas por curso do
[Infocursos/MECI](https://infocursos.medu.pt). Este é um projeto
independente, sem qualquer ligação à DGES ou ao Ministério da Educação.
