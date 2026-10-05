import csv
import json
import urllib.request
import ssl
from datetime import datetime

URL_ANAGRAFICA = "https://www.mimit.gov.it/images/exportCSV/anagrafica_impianti_attivi.csv"
URL_PREZZI = "https://www.mimit.gov.it/images/exportCSV/prezzo_alle_8.csv"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def fetch_data(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=180, context=ctx) as resp:
        return resp.read().decode('utf-8', errors='ignore')

def parse_mimit_date(date_str):
    """Parst das MIMIT Datumsformat (oft 'YYYY-MM-DD HH:MM:SS' oder 'DD/MM/YYYY HH:MM:SS')"""
    if not date_str:
        return datetime.min
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            pass
    return datetime.min

def main():
    print("1. Lade Tankstellen...")
    text_ana = fetch_data(URL_ANAGRAFICA)
    sep_ana = ';' if ';' in text_ana[:500] else '|'
    lines_ana = [l for l in text_ana.splitlines() if l.strip()]
    start_ana = 0
    for idx, l in enumerate(lines_ana[:5]):
        if "idImpianto" in l:
            start_ana = idx
            break

    reader_ana = csv.DictReader(lines_ana[start_ana:], delimiter=sep_ana)
    bz_stations = {}

    for row in reader_ana:
        row = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k}
        if row.get("Provincia", "").upper() == "BZ":
            sid = row.get("idImpianto")
            if sid:
                bz_stations[sid] = {
                    "id": sid,
                    "name": row.get("Nome Impianto") or row.get("Bandiera") or "Tankstelle",
                    "brand": row.get("Bandiera") or "Freie Tankstelle",
                    "address": row.get("Indirizzo", ""),
                    "city": row.get("Comune", ""),
                    "lat": row.get("Latitudine", "").replace(",", "."),
                    "lon": row.get("Longitudine", "").replace(",", "."),
                    "prices": {},
                    "_price_dates": {} # Interner Zwischenspeicher für Datumsabgleich
                }

    print(f"Südtirol-Stationen gefunden: {len(bz_stations)}")

    print("2. Lade Preise...")
    text_prez = fetch_data(URL_PREZZI)
    sep_prez = ';' if ';' in text_prez[:500] else '|'
    lines_prez = [l for l in text_prez.splitlines() if l.strip()]
    start_prez = 0
    for idx, l in enumerate(lines_prez[:5]):
        if "idImpianto" in l:
            start_prez = idx
            break

    reader_prez = csv.DictReader(lines_prez[start_prez:], delimiter=sep_prez)

    BLACKLIST = ["100", "plus", "optima", "v-power", "racing", "additiv", "supreme", "excellium", "special", "hi-q"]

    for row in reader_prez:
        row = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k}
        sid = row.get("idImpianto")
        if sid in bz_stations:
            fuel = row.get("descCarburante", "").lower()
            price_raw = row.get("prezzo", "").replace(",", ".")
            is_self = row.get("isSelf", "0").strip()
            dt_raw = row.get("dtComu", "")

            try:
                pval = float(price_raw)
            except ValueError:
                continue

            if not (1.0 < pval < 2.60):
                continue

            mode = "Self" if is_self == "1" else "Servito"
            msg_date = parse_mimit_date(dt_raw)

            key = None

            # 1. Alpino separat erfassen
            if "alpino" in fuel:
                key = f"Alpino ({mode})"

            # Premium-Kraftstoffe überspringen
            elif any(b in fuel for b in BLACKLIST):
                continue

            # 2. Standard-Diesel
            elif "diesel" in fuel or "gasolio" in fuel:
                key = f"Gasolio ({mode})"

            # 3. Benzin
            elif "benzina" in fuel or "senza piombo" in fuel:
                key = f"Benzina ({mode})"

            # WICHTIG: IMMER die aktuellste Meldung behalten, NICHT min()!
            if key:
                last_date = bz_stations[sid]["_price_dates"].get(key, datetime.min)
                if key not in bz_stations[sid]["prices"] or msg_date >= last_date:
                    bz_stations[sid]["prices"][key] = pval
                    bz_stations[sid]["_price_dates"][key] = msg_date

    # Bereinige interne Hilfsdaten vor dem JSON-Export
    for station in bz_stations.values():
        del station["_price_dates"]

    final_list = [s for s in bz_stations.values() if len(s["prices"]) > 0]
    print(f"Gültige Tankstellen mit Preisen: {len(final_list)}")

    with open("spritpreise_bz.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
