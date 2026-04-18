"""
notify.py — trimite alerte Telegram când scraper-ul eșuează sau reușește.

Configurare în .env:
    TELEGRAM_TOKEN=123456:ABCdef...   ← de la @BotFather
    TELEGRAM_CHAT_ID=-100123456789   ← ID-ul grupului/canalului sau al tău personal
"""

import os
import json
import urllib.request
import urllib.error
from datetime import datetime


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _send(text: str) -> bool:
    token   = _env("TELEGRAM_TOKEN")
    chat_id = _env("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        return False

    url  = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({
        "chat_id":    chat_id,
        "text":       text,
        "parse_mode": "HTML",
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"NOTIFY: nu am putut trimite pe Telegram: {e}")
        return False


def alert_cookie_expired():
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    _send(
        f"🔴 <b>REBS Scraper – Cookie expirat</b>\n"
        f"Data: {now}\n\n"
        f"Scraper-ul a fost redirecționat la pagina de login.\n"
        f"Actualizează <code>REBS_COOKIE</code> în fișierul <code>.env</code> de pe VPS."
    )


def alert_no_results(since_hours: int):
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    _send(
        f"⚠️ <b>REBS Scraper – 0 proprietăți găsite</b>\n"
        f"Data: {now}\n\n"
        f"Nu s-a găsit nicio proprietate din ultimele {since_hours}h.\n"
        f"Posibil: cookie expirat, URL greșit sau CRM offline."
    )


def alert_error(reason: str):
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    _send(
        f"🔴 <b>REBS Scraper – Eroare neașteptată</b>\n"
        f"Data: {now}\n\n"
        f"<code>{reason[:800]}</code>"
    )


def alert_success(count: int, with_phone: int, sheets_id: str):
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    sheets_url = f"https://docs.google.com/spreadsheets/d/{sheets_id}" if sheets_id else ""
    link_line  = f"\n<a href=\"{sheets_url}\">Deschide Sheets</a>" if sheets_url else ""
    _send(
        f"✅ <b>REBS Scraper – Export reușit</b>\n"
        f"Data: {now}\n\n"
        f"Proprietăți noi adăugate: <b>{count}</b>\n"
        f"Cu telefon: {with_phone}"
        f"{link_line}"
    )
