#!/usr/bin/env bash
# run_daily.sh — rulat de cron zilnic la 05:00 ora României
#
# Instalare cron (o singură dată):
#   crontab -e
#   0 3 * * * /home/user/nino/run_daily.sh >> /home/user/nino/logs/cron.log 2>&1
#
# Notă: cron rulează în UTC. 05:00 EET (iarna, UTC+2) = 03:00 UTC
#                            05:00 EEST (vara,  UTC+3) = 02:00 UTC
# Ajustează ora din crontab după anotimp sau folosește TZ=Europe/Bucharest.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

echo "=========================================="
echo " REBS scraper – $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# Încarcă variabilele din .env
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

# Activează virtualenv dacă există
if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
fi

cd "$SCRIPT_DIR"

python scraper.py \
    --headless \
    --since-hours 24 \
    --delay 1.0

echo "Gata – $(date '+%Y-%m-%d %H:%M:%S')"
