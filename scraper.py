"""
CRM REBS – Playwright scraper
==============================
- Citește datele direct din tabelul de listing (ID, tip, locatie, pret)
- Dă click pe butonul "Detalii" al fiecărei proprietăți
- Extrage telefonul de pe pagina de detalii
- Se întoarce și continuă cu următoarea

Usage:
    python scraper.py --cookie "YOUR_COOKIE_STRING"
    set REBS_COOKIE=your_cookie && python scraper.py --headless
"""

import argparse
import os
import sys
import time
import re
from datetime import datetime

from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from deliver import deliver

# ── Config ─────────────────────────────────────────────────────────────────

LISTINGS_URL = "https://mervani-imobiliare.crmrebs.com/market-snapshot/listings"
DOMAIN       = "mervani-imobiliare.crmrebs.com"

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

# ── CLI / env ──────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--cookie",    default="", help="Cookie header string")
    p.add_argument("--output",    default="", help="Fișier .xlsx output")
    p.add_argument("--delay",     type=float, default=0.8)
    p.add_argument("--max-pages", type=int,   default=200)
    p.add_argument("--headless",  action="store_true")
    return p.parse_args()


def get_cookie(args) -> str:
    cookie = args.cookie or os.environ.get("REBS_COOKIE", "")
    if not cookie:
        print("EROARE: cookie lipsește. Folosește --cookie sau REBS_COOKIE.")
        sys.exit(1)
    return cookie


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
    """Returnează (valoare_numerica, valuta)."""
    # Ex: "39,000 €", "353 € / lună", "135.000 €"
    m = re.search(r"([\d\s,.]+)\s*(€|EUR|RON|Lei|\$)", text, re.IGNORECASE)
    if m:
        val    = re.sub(r"[\s,.]", "", m.group(1))
        valuta = m.group(2).upper().replace("LEI", "RON")
        return val, valuta
    return "", ""


def parse_tip_and_tranzactie(text: str) -> tuple[str, str, str, str]:
    """
    Din textul coloanei "Tip proprietate / Caracteristici" extrage:
    (tip_proprietate, tip_tranzactie, camere, suprafata)

    Ex: "Casă / Vilă cu 2 camere de vânzare\nS.U. 107 mp · S.T. 47"
    """
    tip = ""
    tranzactie = ""
    camere = ""
    suprafata = ""

    # Tip proprietate
    for t in ["Apartament", "Casă", "Casa", "Vilă", "Vila", "Teren",
              "Spațiu comercial", "Spatiu comercial", "Garsonieră", "Garsoniera",
              "Duplex", "Penthouse", "Birou", "Depozit", "Hală", "Hala"]:
        if re.search(t, text, re.I):
            tip = t.replace("ă", "a").replace("î", "i").replace("â", "a").replace("ș", "s").replace("ț", "t")
            break

    # Tip tranzactie
    if re.search(r"vânzare|vanzare", text, re.I):
        tranzactie = "Vanzare"
    elif re.search(r"închiriat|inchiriat|închiriere|inchiriere", text, re.I):
        tranzactie = "Inchiriere"

    # Camere
    m = re.search(r"(\d+)\s*camere?", text, re.I)
    if m:
        camere = m.group(1)

    # Suprafata utila (S.U.)
    m = re.search(r"S\.U\.?\s*([\d,\.]+)\s*mp", text, re.I)
    if m:
        suprafata = m.group(1).replace(",", ".")
    else:
        m = re.search(r"([\d,\.]+)\s*mp", text, re.I)
        if m:
            suprafata = m.group(1)

    return tip, tranzactie, camere, suprafata


def parse_location(text: str) -> tuple[str, str]:
    """
    Din textul coloanei Locație extrage (localitate, judet).
    Ex: "Mihai Bravu, Ploiești, jud. Prahova"  → ("Ploiești", "Prahova")
    Ex: "Breaza, jud. Prahova"                  → ("Breaza", "Prahova")
    """
    judet = ""
    localitate = ""

    m = re.search(r"jud\.?\s*([A-ZĂÎÂȘȚ][a-zăîâșț\-]+)", text)
    if m:
        judet = m.group(1)

    # Elimină "jud. Prahova" și ia ultima parte ca localitate
    loc_text = re.sub(r",?\s*jud\.?\s*[A-ZĂÎÂȘȚ][a-zăîâșț\-]+", "", text).strip()
    parts = [p.strip() for p in loc_text.split(",") if p.strip()]
    if parts:
        localitate = parts[-1]  # ultima parte = orașul/comuna

    return localitate, judet


# ── Scraping pagina de listing ─────────────────────────────────────────────

def scrape_listing_row(row) -> dict:
    """
    Extrage datele direct din rândul tabelului de listing, fără să intre pe detalii.
    Returnează dict cu toate câmpurile disponibile (telefon va fi "" până la detalii).
    """
    prop = {k: "" for k in COLUMN_NAMES}

    try:
        cells = row.locator("td").all()
        if len(cells) < 5:
            return prop

        # Coloana 0: checkbox (ignoră)
        # Coloana 1: ID
        id_text = clean(cells[1].inner_text())
        prop["ID"] = id_text  # ex: AP1606137

        # Coloana 2: Imagini (ignoră)

        # Coloana 3: Tip proprietate / Caracteristici
        tip_text = clean(cells[3].inner_text())
        tip, tranzactie, camere, suprafata = parse_tip_and_tranzactie(tip_text)
        prop["Tip Proprietate"] = tip
        prop["Tip Tranzactie"]  = tranzactie
        prop["Camere"]          = camere
        prop["Suprafata (mp)"]  = suprafata

        # Coloana 4: Zile piață / Ultima modif.
        data_text = clean(cells[4].inner_text())
        # Ex: "19 minute\n17 Apr '26 20:21"
        lines = [l.strip() for l in data_text.split("\n") if l.strip()]
        if len(lines) >= 2:
            prop["Data Publicare"] = lines[1]  # "17 Apr '26 20:21"

        # Coloana 5: Locație
        loc_text = clean(cells[5].inner_text())
        localitate, judet = parse_location(loc_text)
        prop["Localitate"] = localitate
        prop["Judet"]      = judet

        # Coloana 6: Preț
        pret_text = clean(cells[6].inner_text())
        prop["Pret"], prop["Valuta"] = parse_price(pret_text)

    except Exception as e:
        print(f"    Eroare la citit rând: {e}")

    return prop


# ── Scraping pagina de detalii ─────────────────────────────────────────────

def scrape_detail_for_phone(page: Page) -> tuple[str, str]:
    """
    Pe pagina de detalii, caută numărul de telefon și link-ul.
    Returnează (telefon, url_curent).
    """
    url   = page.url
    phone = ""

    # Așteaptă să se încarce pagina
    page.wait_for_timeout(1000)
    full_text = clean(page.inner_text("body") or "")

    # 1. Link tel:
    tel_links = page.locator("a[href^='tel:']").all()
    if tel_links:
        try:
            raw   = tel_links[0].get_attribute("href").replace("tel:", "").strip()
            phone = re.sub(r"[\s.\-]", "", raw)
        except Exception:
            pass

    # 2. Click buton "afișează telefon" dacă există
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

    # 3. Regex în text
    if not phone:
        phone = extract_phone(full_text)

    return phone, url


# ── Paginare ───────────────────────────────────────────────────────────────

def get_total_pages(page: Page) -> int:
    """Detectează numărul total de pagini din text-ul de paginare."""
    try:
        # Ex: "Pagina 1, 100+ rezultate" sau "Pagina 1 din 5"
        pag_text = clean(page.locator("text=/[Pp]agina/").first.inner_text())
        m = re.search(r"din\s+(\d+)", pag_text, re.I)
        if m:
            return int(m.group(1))
    except Exception:
        pass

    # Caută linkuri numerice în paginare
    try:
        links = page.locator(".pagination a, nav a").all()
        nums = []
        for a in links:
            try:
                t = clean(a.inner_text())
                if t.isdigit():
                    nums.append(int(t))
            except Exception:
                continue
        if nums:
            return max(nums)
    except Exception:
        pass

    return 1


def has_next_page(page: Page, current: int) -> bool:
    """Verifică dacă există o pagină următoare."""
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
    args        = parse_args()
    cookie      = get_cookie(args)
    output_file = args.output or f"rebs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    delay       = args.delay
    max_pages   = args.max_pages
    headless    = args.headless
    export_dt   = datetime.now()
    all_props: list[dict] = []

    print("=" * 60)
    print("  CRM REBS Scraper")
    print("=" * 60)
    print(f"  Output:   {output_file}")
    print(f"  Headless: {'DA' if headless else 'NU'}")
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

        while current_page <= max_pages:
            listing_url = LISTINGS_URL if current_page == 1 else f"{LISTINGS_URL}?page={current_page}"
            print(f"\n── Pagina {current_page} ──────────────────────────────────────")

            try:
                page.goto(listing_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(1500)
            except Exception as e:
                print(f"  Eroare la navigare: {e}")
                break

            if "login" in page.url.lower() or "signin" in page.url.lower():
                print("  Cookie expirat — redirecționat la login. Oprire.")
                sys.exit(1)

            # ── Pasul 1: colectează toate datele + URL-urile din tabel ──────
            # Facem asta ÎNAINTE de orice navigare, cât pagina e intactă.
            page_entries: list[dict] = []

            rows = page.locator("tbody tr").all()
            if not rows:
                print("  Niciun rând găsit. Ultima pagină.")
                break

            print(f"  {len(rows)} proprietăți — colectez datele din tabel...")

            for row in rows:
                prop = scrape_listing_row(row)
                if not prop.get("ID"):
                    continue

                # Extrage URL-ul butonului Detalii din HTML (fără click)
                try:
                    btn = row.locator("a:has-text('Detalii')").first
                    href = btn.get_attribute("href") or ""
                    if href and not href.startswith("http"):
                        href = f"https://{DOMAIN}{href}"
                    prop["Link"] = href
                except Exception:
                    prop["Link"] = ""

                page_entries.append(prop)

            print(f"  {len(page_entries)} proprietăți valide. Intru pe fiecare...")

            # ── Pasul 2: navighează la fiecare URL de detalii ───────────────
            # Nu mai folosim go_back() — navigăm direct prin URL.
            for i, prop in enumerate(page_entries, start=1):
                detail_url = prop.get("Link", "")

                print(f"  [{i}/{len(page_entries)}] {prop['ID']} — "
                      f"{prop.get('Tip Proprietate','?')} | "
                      f"{prop.get('Pret','')} {prop.get('Valuta','')} | "
                      f"{prop.get('Localitate','')}, {prop.get('Judet','')}")

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

            # ── Pasul 3: verifică dacă există pagina următoare ──────────────
            # Reîncarcă pagina de listing pentru a verifica paginarea
            page.goto(listing_url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(1000)

            if not has_next_page(page, current_page):
                print("\n  Ultima pagină atinsă.")
                break

            current_page += 1

        browser.close()

    print(f"\n{'=' * 60}")
    print(f"  Total: {len(all_props)} proprietăți")
    print(f"  Cu telefon: {sum(1 for p in all_props if p.get('Telefon'))}")
    print(f"{'=' * 60}\n")

    export_excel(all_props, output_file, export_dt)
    deliver(output_file, len(all_props), export_dt, properties=all_props)


if __name__ == "__main__":
    main()
