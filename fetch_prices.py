import csv
import json
import urllib.request
import ssl

URL_ANAGRAFICA = "https://www.mimit.gov.it/images/exportCSV/anagrafica_impianti_attivi.csv"
URL_PREZZI = "https://www.mimit.gov.it/images/exportCSV/prezzo_alle_8.csv"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def get_lines(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=180, context=ctx) as resp:
        content = resp.read().decode('utf-8', errors='ignore')
    return [line.strip() for line in content.splitlines() if line.strip()]

def main():
    print("Lade Stammdaten...")
    lines_ana = get_lines(URL_ANAGRAFICA)
    
    header_idx = 0
    delimiter = ';'
    for i, line in enumerate(lines_ana[:10]):
        if "idImpianto" in line:
            header_idx = i
            delimiter = ';' if ';' in line else '|'
            break

    reader = csv.DictReader(lines_ana[header_idx:], delimiter=delimiter)
    bz_stations = {}
    
    for row in reader:
        c = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k}
        if c.get("Provincia", "").upper() == "BZ":
            sid = c.get("idImpianto")
            if sid:
                bz_stations[sid] = {
                    "id": sid,
                    "name": c.get("Nome Impianto") or c.get("Bandiera") or "Tankstelle",
                    "brand": c.get("Bandiera") or "Freie Tankstelle",
                    "address": c.get("Indirizzo", ""),
                    "city": c.get("Comune", ""),
                    "lat": c.get("Latitudine", "").replace(",", "."),
                    "lon": c.get("Longitudine", "").replace(",", "."),
                    "prices": {}
                }

    print("Lade Preise...")
    lines_prez = get_lines(URL_PREZZI)
    
    p_header_idx = 0
    p_delimiter = ';'
    for i, line in enumerate(lines_prez[:10]):
        if "idImpianto" in line:
            p_header_idx = i
            p_delimiter = ';' if ';' in line else '|'
            break

    p_reader = csv.DictReader(lines_prez[p_header_idx:], delimiter=p_delimiter)
    
    EXCLUDE = ["100", "plus", "optima", "v-power", "racing", "additiv", "supreme", "excellium", "special", "hi-q"]

    for row in p_reader:
        c = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k}
        sid = c.get("idImpianto")
        if sid in bz_stations:
            fuel_raw = c.get("descCarburante", "").lower()
            price_str = c.get("prezzo", "").replace(",", ".").strip()
            is_self = str(c.get("isSelf", "0")).strip() in ["1", "true", "True"]

            # Luxussorten ignorieren
            if any(x in fuel_raw for x in EXCLUDE):
                continue

            try:
                price = float(price_str)
            except ValueError:
                continue

            if not (0.80 < price < 2.70):
                continue

            # Kategorie bestimmen
            cat = None
            if "diesel" in fuel_raw or "gasolio" in fuel_raw:
                cat = "Gasolio"
            elif "benzina" in fuel_raw or "senza piombo" in fuel_raw:
                cat = "Benzina"

            if cat:
                mode = "Self" if is_self else "Servito"
                key = f"{cat} ({mode})"
                
                # Immer den billigsten Preis für diese Kategorie behalten
                if key in bz_stations[sid]["prices"]:
                    bz_stations[sid]["prices"][key] = min(bz_stations[sid]["prices"][key], price)
                else:
                    bz_stations[sid]["prices"][key] = price

    # Speichern
    result = [s for s in bz_stations.values() if len(s["prices"]) > 0]
    with open("spritpreise_bz.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
