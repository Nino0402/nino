"""
CRM REBS – Playwright scraper (mod zilnic)
==========================================
Rulează zilnic la 05:00 ora României, colectează proprietățile postate
în ultimele 24 de ore și le adaugă în Google Sheets.

Usage:
    python scraper.py --cookie "YOUR_COOKIE_STRING" --headless
    python scraper.py --url "https://..." --since-hours 24

Variabile de mediu (sau .env):
    REBS_COOKIE       – șirul de cookie din browser
    REBS_URL          – URL-ul paginii cu filtrele dorite
    DELIVER_SHEETS=1
    GOOGLE_SA_JSON    – calea spre service_account.json
    SHEETS_ID         – ID-ul spreadsheet-ului Google
"""

import argparse
import os
import sys
import time
import re
from datetime import datetime, timedelta, timezone

from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from deliver import deliver
from notify import alert_cookie_expired, alert_no_results, alert_error, alert_success

# ── Config ─────────────────────────────────────────────────────────────────

DEFAULT_URL = "https://mervani-imobiliare.crmrebs.com/market-snapshot/listings"
DOMAIN      = "mervani-imobiliare.crmrebs.com"

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

MONTHS = {
    "ian": 1, "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "mai": 5, "may": 5, "iun": 6, "jun": 6, "iul": 7, "jul": 7,
    "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Fusul orar România (Europe/Bucharest) — UTC+2 iarna, UTC+3 vara.
# Folosim utcnow() + comparăm naive, suficient pentru precizie de 1h.
RO_UTC_OFFSET = 3  # EEST (vara); schimbă în 2 iarna dacă e necesar

# ── CLI / env ──────────────────────────────────────────────────────────────

def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def parse_args():
    p = argparse.ArgumentParser(description="REBS daily scraper")
    p.add_argument("--cookie",       default="",   help="Cookie header string")
    p.add_argument("--url",          default="",   help="URL listing cu filtre")
    p.add_argument("--output",       default="",   help="Fișier .xlsx output (opțional)")
    p.add_argument("--delay",        type=float, default=0.8)
    p.add_argument("--max-pages",    type=int,   default=200)
    p.add_argument("--since-hours",  type=int,   default=24,
                   help="Colectează doar proprietăți din ultimele N ore (0 = toate)")
    p.add_argument("--headless",     action="store_true")
    return p.parse_args()


def get_cookie(args) -> str:
    cookie = args.cookie or _env("REBS_COOKIE")
    if not cookie:
        print("EROARE: cookie lipsește. Folosește --cookie sau REBS_COOKIE.")
        sys.exit(1)
    return cookie


def get_listings_url(args) -> str:
    return args.url or _env("REBS_URL") or DEFAULT_URL


def parse_cookies(cookie_str: str) -> list[dict]:
    cookies = []
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            name, _, value = part.partition("=")
            cookies.append({
                "name":   name.strip(),
                "value":  value.strip(),
                "domain": DOMAIN,
                "path":   "/",
            })
    return cookies


# ── Helpers ────────────────────────────────────────────────────────────────

def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def parse_publish_date(text: str) -> datetime | None:
    """
    Parsează formatul "17 Apr '26 20:21" → datetime naiv în ora României.
    Returnează None dacă formatul nu e recunoscut.
    """
    text = text.strip()
    m = re.match(r"(\d{1,2})\s+(\w{3})\s+'(\d{2})\s+(\d{2}):(\d{2})", text)
    if not m:
        return None
    day, mon_str, yr2, hr, mn = m.groups()
    month = MONTHS.get(mon_str.lower())
    if not month:
        return None
    year = 2000 + int(yr2)
    try:
        return datetime(year, month, int(day), int(hr), int(mn))
    except ValueError:
        return None


def is_recent(date_text: str, since_hours: int) -> bool | None:
    """
    True  = proprietatea e în fereastra de timp
    False = proprietatea e mai veche
    None  = data nu a putut fi parsată (include-o oricum)
    """
    if since_hours <= 0:
        return True
    dt = parse_publish_date(date_text)
    if dt is None:
        return None
    # "acum" în ora României
    now_ro = datetime.utcnow() + timedelta(hours=RO_UTC_OFFSET)
    cutoff = now_ro - timedelta(hours=since_hours)
    return dt >= cutoff


def extract_phone(text: str) -> str:
    patterns = [
        r"\+40\s*7\d{2}[\s.\-]?\d{3}[\s.\-]?\d{3}",
        r"\b07\d{2}[\s.\-]?\d{3}[\s.\-]?\d{3}\b",
        r"\b02\d[\s.\-]?\d{3}[\s.\-]?\d{3}\b",
        r"\b03\d[\s.\-]?\d{3}[\s.\-]?\d{3}\b",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return re.sub(r"[\s.\-]", "", m.group()).strip()
    return ""


def parse_price(text: str) -> tuple[str, str]:
    m = re.search(r"([\d\s,.]+)\s*(€|EUR|RON|Lei|\$)", text, re.IGNORECASE)
    if m:
        val    = re.sub(r"[\s,.]", "", m.group(1))
        valuta = m.group(2).upper().replace("LEI", "RON")
        return val, valuta
    return "", ""


def parse_tip_and_tranzactie(text: str) -> tuple[str, str, str, str]:
    tip = ""
    tranzactie = ""
    camere = ""
    suprafata = ""

    for t in ["Apartament", "Casă", "Casa", "Vilă", "Vila", "Teren",
              "Spațiu comercial", "Spatiu comercial", "Garsonieră", "Garsoniera",
              "Duplex", "Penthouse", "Birou", "Depozit", "Hală", "Hala"]:
        if re.search(t, text, re.I):
            tip = t.replace("ă", "a").replace("î", "i").replace("â", "a").replace("ș", "s").replace("ț", "t")
            break

    if re.search(r"vânzare|vanzare", text, re.I):
        tranzactie = "Vanzare"
    elif re.search(r"închiriat|inchiriat|închiriere|inchiriere", text, re.I):
        tranzactie = "Inchiriere"

    m = re.search(r"(\d+)\s*camere?", text, re.I)
    if m:
        camere = m.group(1)

    m = re.search(r"S\.U\.?\s*([\d,\.]+)\s*mp", text, re.I)
    if m:
        suprafata = m.group(1).replace(",", ".")
    else:
        m = re.search(r"([\d,\.]+)\s*mp", text, re.I)
        if m:
            suprafata = m.group(1)

    return tip, tranzactie, camere, suprafata


def parse_location(text: str) -> tuple[str, str]:
    judet = ""
    localitate = ""

    m = re.search(r"jud\.?\s*([A-ZĂÎÂȘȚ][a-zăîâșț\-]+)", text)
    if m:
        judet = m.group(1)

    loc_text = re.sub(r",?\s*jud\.?\s*[A-ZĂÎÂȘȚ][a-zăîâșț\-]+", "", text).strip()
    parts = [p.strip() for p in loc_text.split(",") if p.strip()]
    if parts:
        localitate = parts[-1]

    return localitate, judet


# ── Scraping pagina de listing ─────────────────────────────────────────────

def scrape_listing_row(row) -> dict:
    prop = {k: "" for k in COLUMN_NAMES}

    try:
        cells = row.locator("td").all()
        if len(cells) < 5:
            return prop

        prop["ID"] = clean(cells[1].inner_text())

        tip_text = clean(cells[3].inner_text())
        tip, tranzactie, camere, suprafata = parse_tip_and_tranzactie(tip_text)
        prop["Tip Proprietate"] = tip
        prop["Tip Tranzactie"]  = tranzactie
        prop["Camere"]          = camere
        prop["Suprafata (mp)"]  = suprafata

        data_text = clean(cells[4].inner_text())
        lines = [l.strip() for l in data_text.split("\n") if l.strip()]
        if len(lines) >= 2:
            prop["Data Publicare"] = lines[1]

        loc_text = clean(cells[5].inner_text())
        localitate, judet = parse_location(loc_text)
        prop["Localitate"] = localitate
        prop["Judet"]      = judet

        pret_text = clean(cells[6].inner_text())
        prop["Pret"], prop["Valuta"] = parse_price(pret_text)

    except Exception as e:
        print(f"    Eroare la citit rând: {e}")

    return prop


# ── Scraping pagina de detalii ─────────────────────────────────────────────

def scrape_detail_for_phone(page: Page) -> tuple[str, str]:
    url   = page.url
    phone = ""

    page.wait_for_timeout(1000)
    full_text = clean(page.inner_text("body") or "")

    tel_links = page.locator("a[href^='tel:']").all()
    if tel_links:
        try:
            raw   = tel_links[0].get_attribute("href").replace("tel:", "").strip()
            phone = re.sub(r"[\s.\-]", "", raw)
        except Exception:
            pass

    if not phone:
        btn_selectors = [
            "button:has-text('Telefon')",
            "button:has-text('telefon')",
            "button:has-text('Afișează')",
            "button:has-text('numărul')",
            "[class*='phone']",
            "[class*='tel']",
            "a:has-text('07')",
            "span:has-text('07')",
        ]
        for sel in btn_selectors:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=800):
                    el.click()
                    page.wait_for_timeout(800)
                    full_text = clean(page.inner_text("body") or "")
                    break
            except Exception:
                continue

    if not phone:
        phone = extract_phone(full_text)

    return phone, url


# ── Paginare ───────────────────────────────────────────────────────────────

def has_next_page(page: Page, current: int) -> bool:
    selectors = [
        "a[rel='next']",
        f"a[href*='page={current + 1}']",
        ".pagination a:has-text('»')",
        ".pagination a:has-text('>')",
        f".pagination a:has-text('{current + 1}')",
    ]
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=500):
                return True
        except Exception:
            continue
    return False


# ── Excel export ───────────────────────────────────────────────────────────

HEADER_FILL  = PatternFill("solid", fgColor="1F4E79")
ROW_FILL_ODD = PatternFill("solid", fgColor="DCE6F1")
ROW_FILL_EVN = PatternFill("solid", fgColor="FFFFFF")
HEADER_FONT  = Font(bold=True, color="FFFFFF", size=11)
THIN_BORDER  = Border(
    bottom=Side(style="thin", color="AAAAAA"),
    right=Side(style="thin",  color="DDDDDD"),
)


def export_excel(properties: list[dict], filepath: str, export_dt: datetime):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Anunturi"

    ws.append(COLUMN_NAMES)
    for col_idx in range(1, len(COLUMN_NAMES) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER
    ws.row_dimensions[1].height = 28

    for row_num, prop in enumerate(properties, start=2):
        ws.append([prop.get(col, "") for col in COLUMN_NAMES])
        fill = ROW_FILL_ODD if row_num % 2 == 0 else ROW_FILL_EVN
        for col_idx in range(1, len(COLUMN_NAMES) + 1):
            cell = ws.cell(row=row_num, column=col_idx)
            cell.fill = fill
            cell.alignment = Alignment(vertical="center")
            cell.border = THIN_BORDER

    for col_idx, col_name in enumerate(COLUMN_NAMES, start=1):
        max_len = len(col_name)
        for row_num in range(2, len(properties) + 2):
            val = str(ws.cell(row=row_num, column=col_idx).value or "")
            max_len = max(max_len, len(val))
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 4, 55)

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    ws2 = wb.create_sheet("Sumar")
    sumar = [
        ("Export la",      export_dt.strftime("%Y-%m-%d %H:%M:%S")),
        ("Total anunturi", len(properties)),
        ("Vanzare",        sum(1 for p in properties if p.get("Tip Tranzactie") == "Vanzare")),
        ("Inchiriere",     sum(1 for p in properties if p.get("Tip Tranzactie") == "Inchiriere")),
        ("Cu telefon",     sum(1 for p in properties if p.get("Telefon"))),
        ("Cu pret",        sum(1 for p in properties if p.get("Pret"))),
    ]
    ws2.column_dimensions["A"].width = 25
    ws2.column_dimensions["B"].width = 30
    for r in sumar:
        ws2.append(list(r))
    for i in range(1, len(sumar) + 1):
        ws2.cell(row=i, column=1).font = Font(bold=True)

    wb.save(filepath)
    print(f"Salvat: {filepath}")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    args          = parse_args()
    cookie        = get_cookie(args)
    listings_url  = get_listings_url(args)
    since_hours   = args.since_hours
    output_file   = args.output or f"rebs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    delay         = args.delay
    max_pages     = args.max_pages
    headless      = args.headless
    export_dt     = datetime.now()
    sheets_id     = _env("SHEETS_ID")
    all_props: list[dict] = []

    try:
        _run(args, cookie, listings_url, since_hours, output_file, delay,
             max_pages, headless, export_dt, sheets_id, all_props)
    except SystemExit:
        raise
    except Exception as exc:
        import traceback
        msg = traceback.format_exc()
        print(f"\nEROARE NEAȘTEPTATĂ:\n{msg}")
        alert_error(msg)
        sys.exit(2)


def _run(args, cookie, listings_url, since_hours, output_file, delay,
         max_pages, headless, export_dt, sheets_id, all_props):

    print("=" * 60)
    print("  CRM REBS Scraper – mod zilnic")
    print("=" * 60)
    print(f"  URL:          {listings_url}")
    print(f"  Ultimele:     {since_hours}h  (0 = toate)")
    print(f"  Output:       {output_file}")
    print(f"  Headless:     {'DA' if headless else 'NU'}")
    print()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, slow_mo=200)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
            ),
        )
        context.add_cookies(parse_cookies(cookie))
        page = context.new_page()

        current_page = 1
        stop_pagination = False  # setat True când am ieșit din fereastra de 24h

        while current_page <= max_pages and not stop_pagination:
            listing_url = listings_url if current_page == 1 else f"{listings_url}{'&' if '?' in listings_url else '?'}page={current_page}"
            print(f"\n── Pagina {current_page} ──────────────────────────────────────")

            try:
                page.goto(listing_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(1500)
            except Exception as e:
                print(f"  Eroare la navigare: {e}")
                break

            if "login" in page.url.lower() or "signin" in page.url.lower():
                print("  Cookie expirat — redirecționat la login. Oprire.")
                alert_cookie_expired()
                sys.exit(1)

            rows = page.locator("tbody tr").all()
            if not rows:
                print("  Niciun rând găsit. Ultima pagină.")
                break

            print(f"  {len(rows)} proprietăți — colectez datele din tabel...")

            page_entries: list[dict] = []
            for row in rows:
                prop = scrape_listing_row(row)
                if not prop.get("ID"):
                    continue

                # ── Filtrare după dată ──────────────────────────────────────
                date_text = prop.get("Data Publicare", "")
                recent = is_recent(date_text, since_hours)

                if recent is False:
                    # Dacă lista e sortată newest-first, putem opri paginarea.
                    # Dacă nu e sortată, comentează linia de mai jos.
                    print(f"  Proprietate mai veche de {since_hours}h ({date_text}) — opresc paginarea.")
                    stop_pagination = True
                    break

                try:
                    btn = row.locator("a:has-text('Detalii')").first
                    href = btn.get_attribute("href") or ""
                    if href and not href.startswith("http"):
                        href = f"https://{DOMAIN}{href}"
                    prop["Link"] = href
                except Exception:
                    prop["Link"] = ""

                page_entries.append(prop)

            print(f"  {len(page_entries)} proprietăți recente pe această pagină.")

            for i, prop in enumerate(page_entries, start=1):
                detail_url = prop.get("Link", "")

                print(f"  [{i}/{len(page_entries)}] {prop['ID']} — "
                      f"{prop.get('Tip Proprietate','?')} | "
                      f"{prop.get('Pret','')} {prop.get('Valuta','')} | "
                      f"{prop.get('Localitate','')}, {prop.get('Judet','')} | "
                      f"{prop.get('Data Publicare','')}")

                if detail_url:
                    try:
                        page.goto(detail_url, wait_until="domcontentloaded", timeout=20000)
                        phone, final_url = scrape_detail_for_phone(page)
                        prop["Telefon"] = phone
                        prop["Link"]    = final_url or detail_url
                        print(f"    📞 {phone}" if phone else "    fără telefon")
                    except Exception as e:
                        print(f"    Eroare detalii: {e}")
                else:
                    print("    fără link Detalii")

                all_props.append(prop)
                time.sleep(delay)

            print(f"  Total acumulat: {len(all_props)}")

            if stop_pagination:
                break

            page.goto(listing_url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(1000)

            if not has_next_page(page, current_page):
                print("\n  Ultima pagină atinsă.")
                break

            current_page += 1

        browser.close()

    print(f"\n{'=' * 60}")
    print(f"  Total proprietăți noi (ultimele {since_hours}h): {len(all_props)}")
    print(f"  Cu telefon: {sum(1 for p in all_props if p.get('Telefon'))}")
    print(f"{'=' * 60}\n")

    if not all_props:
        print("Nicio proprietate nouă. Nu se exportă nimic.")
        alert_no_results(since_hours)
        return

    if args.output:
        export_excel(all_props, output_file, export_dt)

    deliver(output_file if args.output else "", len(all_props), export_dt, properties=all_props)

    with_phone = sum(1 for p in all_props if p.get("Telefon"))
    alert_success(len(all_props), with_phone, sheets_id)


if __name__ == "__main__":
    main()
