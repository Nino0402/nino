"""
deliver.py — trimite Excel-ul pe email și/sau Google Drive după export.

Configurare prin variabile de mediu (sau fișier .env):

  EMAIL:
    DELIVER_EMAIL=1
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=tine@gmail.com
    SMTP_PASS=parola_aplicatie_gmail   ← NU parola contului, vezi README
    MAIL_TO=destinatar@gmail.com       ← mai multe separate prin virgulă

  GOOGLE DRIVE:
    DELIVER_DRIVE=1
    DRIVE_FOLDER_ID=1AbCdEfGhIjKlMnOp  ← ID-ul folderului din URL
    GOOGLE_SA_JSON=/path/to/service_account.json
"""

import os
import smtplib
import sys
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from pathlib import Path


# ── Helpers ────────────────────────────────────────────────────────────────

def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _load_dotenv():
    """Citește .env dacă există (fără python-dotenv)."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            # Nu suprascrie variabile deja setate în shell
            if key.strip() not in os.environ:
                os.environ[key.strip()] = val.strip().strip('"').strip("'")


# ── Email ──────────────────────────────────────────────────────────────────

def send_email(filepath: str, total: int, export_dt: datetime):
    """Trimite Excel-ul ca atașament pe email prin SMTP."""
    host     = _env("SMTP_HOST", "smtp.gmail.com")
    port     = int(_env("SMTP_PORT", "587"))
    user     = _env("SMTP_USER")
    password = _env("SMTP_PASS")
    to_raw   = _env("MAIL_TO")

    if not all([user, password, to_raw]):
        print("EMAIL: lipsesc SMTP_USER / SMTP_PASS / MAIL_TO — skip.")
        return

    recipients = [r.strip() for r in to_raw.split(",") if r.strip()]
    subject = (
        f"REBS Export – {total} anunțuri – "
        f"{export_dt.strftime('%d.%m.%Y %H:%M')}"
    )
    body = (
        f"Salut,\n\n"
        f"Atașat găsești exportul REBS din {export_dt.strftime('%d.%m.%Y la %H:%M')}.\n"
        f"Total anunțuri: {total}\n\n"
        f"Export generat automat de scraper.py\n"
    )

    msg = MIMEMultipart()
    msg["From"] = user
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with open(filepath, "rb") as f:
        part = MIMEApplication(f.read(), Name=Path(filepath).name)
        part["Content-Disposition"] = f'attachment; filename="{Path(filepath).name}"'
        msg.attach(part)

    try:
        print(f"EMAIL: conectare la {host}:{port}...")
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(user, password)
            server.sendmail(user, recipients, msg.as_bytes())
        print(f"EMAIL: trimis către {', '.join(recipients)}")
    except smtplib.SMTPAuthenticationError:
        print("EMAIL EROARE: autentificare eșuată. Verifică SMTP_USER și SMTP_PASS.")
        print("  Gmail: folosește o 'Parolă de aplicație', nu parola contului.")
        print("  https://myaccount.google.com/apppasswords")
    except Exception as e:
        print(f"EMAIL EROARE: {e}")


# ── Google Drive ───────────────────────────────────────────────────────────

def upload_drive(filepath: str):
    """Încarcă fișierul pe Google Drive folosind un Service Account."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        print("DRIVE: lipsesc librăriile. Rulează:")
        print("  pip install google-auth google-api-python-client")
        return

    sa_json      = _env("GOOGLE_SA_JSON")
    folder_id    = _env("DRIVE_FOLDER_ID")

    if not sa_json:
        print("DRIVE: lipsește GOOGLE_SA_JSON — skip.")
        return
    if not Path(sa_json).exists():
        print(f"DRIVE EROARE: fișierul {sa_json} nu există.")
        return

    SCOPES = ["https://www.googleapis.com/auth/drive.file"]
    try:
        creds = service_account.Credentials.from_service_account_file(
            sa_json, scopes=SCOPES
        )
        service = build("drive", "v3", credentials=creds, cache_discovery=False)

        file_meta = {"name": Path(filepath).name}
        if folder_id:
            file_meta["parents"] = [folder_id]

        media = MediaFileUpload(
            filepath,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            resumable=True,
        )
        print("DRIVE: se încarcă fișierul...")
        result = (
            service.files()
            .create(body=file_meta, media_body=media, fields="id,webViewLink")
            .execute()
        )
        print(f"DRIVE: încărcat cu succes!")
        print(f"  Link: {result.get('webViewLink', 'n/a')}")
        print(f"  ID:   {result.get('id')}")
    except Exception as e:
        print(f"DRIVE EROARE: {e}")


# ── Entry point ────────────────────────────────────────────────────────────

def deliver(filepath: str, total: int, export_dt: datetime, properties: list = None):
    _load_dotenv()
    did_something = False

    if _env("DELIVER_EMAIL") == "1":
        send_email(filepath, total, export_dt)
        did_something = True

    if _env("DELIVER_DRIVE") == "1":
        upload_drive(filepath)
        did_something = True

    if _env("DELIVER_SHEETS") == "1":
        if properties is None:
            print("SHEETS: lista de proprietăți lipsește — skip.")
        else:
            from sheets import upload_to_sheets
            upload_to_sheets(properties, export_dt)
        did_something = True

    if not did_something:
        print("LIVRARE: nicio metodă activată (DELIVER_EMAIL / DELIVER_DRIVE / DELIVER_SHEETS = 1).")
