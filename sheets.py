"""
sheets.py — adaugă rânduri noi în Google Sheets, nu modifică ce există deja.

Logică simplă:
  - Citește ID-urile deja existente în sheet
  - Adaugă la final doar proprietățile cu ID nou
  - Nu șterge, nu modifică, nu atinge nimic existent

Configurare în .env:
    DELIVER_SHEETS=1
    GOOGLE_SA_JSON=/home/user/rebs-scraper/service_account.json
    SHEETS_ID=1AbCdEfGhIjKlMnOpQrStUvWxYz
"""

import os
from datetime import datetime
from pathlib import Path

COLUMN_NAMES = [
    "ID",
    "Tip Proprietate",
    "Tip Tranzactie",
    "Suprafata (mp)",
    "Camere",
    "Pret",
    "Valuta",
    "Localitate",
    "Judet",
    "Telefon",
    "Data Publicare",
    "Link",
]


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def upload_to_sheets(properties: list[dict], export_dt: datetime):
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        print("SHEETS: lipsesc librăriile. Rulează: pip install gspread google-auth")
        return

    sa_json   = _env("GOOGLE_SA_JSON")
    sheets_id = _env("SHEETS_ID")

    if not sa_json or not sheets_id:
        print("SHEETS: lipsește GOOGLE_SA_JSON sau SHEETS_ID — skip.")
        return
    if not Path(sa_json).exists():
        print(f"SHEETS EROARE: {sa_json} nu există.")
        return

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
    ]

    try:
        creds  = Credentials.from_service_account_file(sa_json, scopes=SCOPES)
        client = gspread.authorize(creds)
        sh     = client.open_by_key(sheets_id)
    except Exception as e:
        print(f"SHEETS EROARE conectare: {e}")
        return

    # ── Obține sau creează sheet-ul ───────────────────────────────────────
    try:
        ws = sh.worksheet("Anunturi")
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title="Anunturi", rows=5000, cols=len(COLUMN_NAMES))
        ws.append_row(COLUMN_NAMES, value_input_option="USER_ENTERED")
        _format_header(sh, ws)
        print("SHEETS: sheet 'Anunturi' creat.")

    # Verifică dacă are header, adaugă dacă nu
    first_row = ws.row_values(1)
    if first_row != COLUMN_NAMES:
        ws.insert_row(COLUMN_NAMES, index=1, value_input_option="USER_ENTERED")
        _format_header(sh, ws)

    # ── Citește ID-urile existente ────────────────────────────────────────
    existing_ids = set()
    try:
        id_col = ws.col_values(1)  # coloana A = ID
        existing_ids = {str(v).strip() for v in id_col[1:] if v}  # skip header
    except Exception:
        pass

    print(f"SHEETS: {len(existing_ids)} proprietăți deja în sheet.")

    # ── Filtrează doar proprietățile noi ──────────────────────────────────
    new_rows = []
    for prop in properties:
        prop_id = str(prop.get("ID", "")).strip()
        if prop_id and prop_id in existing_ids:
            continue  # deja există, skip
        new_rows.append([str(prop.get(col, "")) for col in COLUMN_NAMES])

    if not new_rows:
        print("SHEETS: nicio proprietate nouă — sheet-ul e deja la zi.")
        return

    # ── Adaugă rândurile noi la final ─────────────────────────────────────
    print(f"SHEETS: se adaugă {len(new_rows)} proprietăți noi...")
    ws.append_rows(new_rows, value_input_option="USER_ENTERED")
    print(f"SHEETS: {len(new_rows)} rânduri adăugate cu succes.")

    # Extinde sheet-ul dacă e necesar
    total = len(existing_ids) + len(new_rows) + 100
    if ws.row_count < total:
        ws.add_rows(500)

    url = f"https://docs.google.com/spreadsheets/d/{sheets_id}"
    print(f"  Link: {url}")


def _format_header(sh, ws):
    try:
        last_col = chr(ord("A") + len(COLUMN_NAMES) - 1)
        ws.format(f"A1:{last_col}1", {
            "backgroundColor": {"red": 0.12, "green": 0.31, "blue": 0.47},
            "textFormat": {
                "bold": True,
                "foregroundColor": {"red": 1, "green": 1, "blue": 1},
            },
            "horizontalAlignment": "CENTER",
        })
        sh.batch_update({"requests": [{
            "updateSheetProperties": {
                "properties": {
                    "sheetId": ws.id,
                    "gridProperties": {"frozenRowCount": 1},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        }]})
    except Exception:
        pass
