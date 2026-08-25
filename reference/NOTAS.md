# Notas sobre as fontes

## dges.gov.pt/coloc/{ano} — resultados da época (efémero)

- **Desaparece no fim da época**: os anos anteriores respondem 404. Arquivar
  cada fase no dia em que sai é a única garantia. O histórico 2018–2025 foi
  recuperado do Arquivo.pt (proveniência em `arquivo_pt.json` junto a cada
  ficheiro).
- O ficheiro `cna{aa}_{f}f_resultados.xls` é a fonte central: todos os pares
  com vagas, colocados, nota do último colocado pelo contingente geral e
  sobras. É .xls antigo (BIFF); convertemos para CSV com LibreOffice headless
  e versionamos ambos.
- **Cabeçalhos mudam entre anos e fases**: colunas extra de desempate a
  partir de ~2024, «Vagas Iniciais 3F» na 3ª fase, «Sobras para 2ª fase» vs
  «Vagas Sobrantes». O build mapeia por nome, nunca por posição.
- Na 1ª fase a nota é «pelo contingente geral»; nas fases seguintes o
  cabeçalho diz só «Nota do últ. colocado». Tratamos como a mesma série.
- Total oficial da 1ª fase de 2026 (comunicado DGES): 49 991 colocados. A
  coluna «Colocados» soma 49 400; com desempates e sem-classificação-final
  chega-se ao valor anunciado. A validação externa usa tolerância de 2%.
- As listagens por estabelecimento (col{f}listamin.asp) publicam a nota por
  curso; **as listas nominais de colocados não são arquivadas** — contêm
  nomes de estudantes e não têm uso estatístico aqui.
- Letras do índice do guia sem cursos (K, W, …) respondem **500**, não
  página vazia.

## dges.gov.pt/guias — guia da candidatura (estável)

- Encoding **windows-1252** declarado como iso-8859-1; nunca usar
  `resp.text` do requests (adivinha mal), sempre `content.decode("windows-1252")`.
- `detcursopi.asp?codc=&code=` traz estatísticas dos 3 anos anteriores,
  incluindo o que os XLS não têm: candidatos (total e em 1ª opção, por
  sexo) e médias dos colocados. A DGES **revê estes números silenciosamente**
  — daí o snapshot SHA-256.
- Códigos de curso podem ser alfanuméricos (L344, 8031, 9081).

## infocursos.medu.pt

- `bds.asp` tem XLSX/ODS anuais desde 2015. Domínio antigo infocursos.mec.pt
  redireciona. (Por integrar — fase 3.)

## Arquivo.pt

- CDX: `https://arquivo.pt/wayback/cdx?url=…&output=json` (um JSON por linha).
- Conteúdo original sem moldura: `https://arquivo.pt/noFrame/replay/{ts}id_/{url}`.
- 2018 é o primeiro ano com os XLS de resultados capturados; 2014–2017 não têm.

## Série longa 1997–2017

A página «Estatísticas do Acesso ao Ensino Superior Público – 1997 a 2025»
(plid=593) só aloja os XLS por par de 2019–2025 — os mesmos que temos via
Arquivo.pt. O período 1997–2017 existe apenas em PDF/portais antigos
(«CNA em números 2014–2018», PowerBI 2019) sem forma estruturada; a série
nacional do esRadar começa por isso em 2018, reconstruída par a par.

## Cobertura parcial de folhas do Infocursos

«Numero Inscritos» (série de inscritos por ano letivo) só cobre ~2500 dos
3685 pares — cursos grandes como Economia/ISCTE ficam de fora. O bloco
`inscritos_serie` é por isso opcional na ficha.

## Horizonte temporal

Decisão de projeto (2026-08): o portal trabalha **de 2018 em diante** — é
onde todas as fontes estruturadas coincidem (XLS de resultados via
Arquivo.pt começam em 2018). `ANO_MINIMO` em build.py.

## Guias antigos (Arquivo.pt)

O guia é reescrito anualmente no mesmo URL; uma captura entre julho de Y e
abril de Y+1 pertence à edição Y. As edições de 2020 e 2023 (ingest/
guias_antigos.py) dão candidatos por sexo/1ª opção e médias dos colocados
de 2017-2022 (cortado a 2018 no build). O HTML antigo é igual ao atual —
`media_secundario` só existe nas edições recentes.

## Fontes avaliadas e descartadas/adiada

- **DGES bolsas de estudo**: os XLSX públicos (mapsintesegeral/
  mapindeferimentos) são sumários processuais nacionais (Total/Público/
  Privado) — não há bolseiros por instituição ou curso. Descartada.
- **DGEEC (RAIDES, exames nacionais)**: em 2026-08 a infraestrutura está
  inoperacional — API do site novo responde 502, os portais legados
  apontam para o domínio extinto dgeec.mec.pt, e o dados.gov.pt não tem
  os datasets de exames. Reavaliar; alternativa: pedido formal de dados.
- **PORDATA**: a API mudou na renovação do site (404 nos endpoints
  antigos); irrelevante com o horizonte 2018+ (a nossa série própria cobre).
- **InfoEscolas**: os XLSX de secundário têm demografia/percursos, não
  médias de exames por prova.
