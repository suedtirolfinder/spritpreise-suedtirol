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
    print("1. Lade Stammdaten...")
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
                    "raw_fuels": {
                        "Gasolio": [],
                        "Benzina": []
                    }
                }

    print(f"Stationen BZ: {len(bz_stations)}")

    print("2. Lade Preise...")
    lines_prez = get_lines(URL_PREZZI)
    
    p_header_idx = 0
    p_delimiter = ';'
    for i, line in enumerate(lines_prez[:10]):
        if "idImpianto" in line:
            p_header_idx = i
            p_delimiter = ';' if ';' in line else '|'
            break

    p_reader = csv.DictReader(lines_prez[p_header_idx:], delimiter=p_delimiter)
    
    PREMIUM_BLACKLIST = ["100", "plus", "optima", "v-power", "racing", "additiv", "supreme", "excellium", "special"]

    for row in p_reader:
        c = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k}
        sid = c.get("idImpianto")
        if sid in bz_stations:
            fuel_desc = c.get("descCarburante", "").lower().strip()
            price_raw = c.get("prezzo", "").replace(",", ".").strip()

            # Spezialsorten wie 100 Oktan rausfiltern
            if any(term in fuel_desc for term in PREMIUM_BLACKLIST):
                continue

            fuel_cat = None
            if "diesel" in fuel_desc or "gasolio" in fuel_desc:
                fuel_cat = "Gasolio"
            elif "benzina" in fuel_desc:
                fuel_cat = "Benzina"

            if not fuel_cat:
                continue

            try:
                pval = float(price_raw)
                if 1.0 < pval < 2.60:
                    bz_stations[sid]["raw_fuels"][fuel_cat].append(pval)
            except ValueError:
                pass

    # Preise zuweisen: Der kleinste Preis ist IMMER Self, der teurere Servito!
    final_list = []
    for sid, s in bz_stations.items():
        prices = {}
        for fcat in ["Gasolio", "Benzina"]:
            arr = sorted(s["raw_fuels"][fcat])
            if len(arr) == 1:
                # Nur ein Preis gemeldet: gilt für Self
                prices[f"{fcat} (Self)"] = arr[0]
            elif len(arr) >= 2:
                # Günstigster ist Self, Höchster ist Servito
                prices[f"{fcat} (Self)"] = arr[0]
                prices[f"{fcat} (Servito)"] = arr[-1]

        if len(prices) > 0:
            final_list.append({
                "id": s["id"],
                "name": s["name"],
                "brand": s["brand"],
                "address": s["address"],
                "city": s["city"],
                "lat": s["lat"],
                "lon": s["lon"],
                "prices": prices
            })

    print(f"Fertige Stationen: {len(final_list)}")

    with open("spritpreise_bz.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
