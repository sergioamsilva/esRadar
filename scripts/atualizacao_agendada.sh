#!/usr/bin/env bash
# Corre diariamente na janela da época (agosto-outubro) via cron:
#   0 7 * 8-10 * /home/parallels/projects/esRadar/scripts/atualizacao_agendada.sh
# Tenta arquivar a fase seguinte à última arquivada; sai em silêncio se a
# DGES ainda não a publicou (o arquivador falha alto quando a página existe
# mas mudou de formato — esse erro é para ser visto).
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON=.venv/bin/python
REGISTO=data/snapshots/registo
mkdir -p "$REGISTO"
LOG="$REGISTO/$(date +%F).log"

ULTIMA=$($PYTHON -c "import json,pathlib; f=pathlib.Path('data/out/epoca.json'); print(max(json.loads(f.read_text())['fases_arquivadas'], default=0))")
PROXIMA=$((ULTIMA + 1))
if [ "$PROXIMA" -gt 3 ]; then
  echo "época completa (3 fases arquivadas)" | tee -a "$LOG"
  exit 0
fi

if $PYTHON -m ingest.coloc --fase "$PROXIMA" >>"$LOG" 2>&1; then
  $PYTHON atualizar.py --fase "$PROXIMA" >>"$LOG" 2>&1
  echo "fase $PROXIMA arquivada — rever git diff de data/ e fazer commit" | tee -a "$LOG"
else
  echo "fase $PROXIMA ainda não disponível ($(date))" >>"$LOG"
fi
