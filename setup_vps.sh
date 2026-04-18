#!/usr/bin/env bash
# setup_vps.sh — instalare completă pe VPS (rulează o singură dată ca root sau cu sudo)
#
# Presupune:
#   - Ubuntu/Debian cu Python 3.11+
#   - Fișierul .env deja completat în /home/$USER/nino/
#   - service_account.json deja pus în locul indicat în .env

set -euo pipefail

USER_NAME="${SUDO_USER:-$USER}"
PROJECT_DIR="/home/$USER_NAME/nino"

echo "==> Instalare pachete sistem..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip

echo "==> Creare virtualenv..."
python3 -m venv "$PROJECT_DIR/venv"
source "$PROJECT_DIR/venv/bin/activate"

echo "==> Instalare dependențe Python..."
pip install -q -r "$PROJECT_DIR/requirements.txt"

echo "==> Instalare Chromium pentru Playwright..."
playwright install chromium
playwright install-deps chromium

echo "==> Creare director logs..."
mkdir -p "$PROJECT_DIR/logs"
chown "$USER_NAME:$USER_NAME" "$PROJECT_DIR/logs"

echo "==> Instalare servicii systemd..."
# Înlocuiește %i cu numele real de utilizator
SERVICE_DEST="/etc/systemd/system/rebs-scraper@$USER_NAME.service"
TIMER_DEST="/etc/systemd/system/rebs-scraper@$USER_NAME.timer"

sed "s|%i|$USER_NAME|g" "$PROJECT_DIR/rebs-scraper.service" > "$SERVICE_DEST"
cp "$PROJECT_DIR/rebs-scraper.timer" "$TIMER_DEST"

systemctl daemon-reload
systemctl enable "rebs-scraper@$USER_NAME.timer"
systemctl start  "rebs-scraper@$USER_NAME.timer"

echo ""
echo "✓ Instalare completă!"
echo ""
echo "Comenzi utile:"
echo "  systemctl status rebs-scraper@$USER_NAME.timer   # stare timer"
echo "  systemctl list-timers rebs-scraper*              # când rulează următorul"
echo "  journalctl -u rebs-scraper@$USER_NAME -f         # log live"
echo "  tail -f $PROJECT_DIR/logs/scraper.log            # log fișier"
echo ""
echo "Test manual (rulează acum, fără să aștepți 05:00):"
echo "  systemctl start rebs-scraper@$USER_NAME"
