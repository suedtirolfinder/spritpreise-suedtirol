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
                    "self_gasolio": [],
                    "serv_gasolio": [],
                    "self_benzina": [],
                    "serv_benzina": []
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
    
    # Unerwünschte Additive / Luxussorten ignorieren
    EXCLUDE_KEYWORDS = ["100", "plus", "optima", "v-power", "racing", "additiv", "supreme", "excellium", "special", "hi-q"]

    for row in p_reader:
        c = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k}
        sid = c.get("idImpianto")
        if sid in bz_stations:
            fuel_desc = c.get("descCarburante", "").lower().strip()
            price_raw = c.get("prezzo", "").replace(",", ".").strip()
            is_self = str(c.get("isSelf", "0")).strip() in ["1", "true", "True"]

            # Luxustreibstoffe überspringen
            if any(term in fuel_desc for term in EXCLUDE_KEYWORDS):
                continue

            try:
                pval = float(price_raw)
            except ValueError:
                continue

            if not (1.0 < pval < 2.80):
                continue

            # Zuordnung Diesel
            if "diesel" in fuel_desc or "gasolio" in fuel_desc:
                if is_self:
                    bz_stations[sid]["self_gasolio"].append(pval)
                else:
                    bz_stations[sid]["serv_gasolio"].append(pval)

            # Zuordnung Benzin
            elif "benzina" in fuel_desc or "senza piombo" in fuel_desc:
                if is_self:
                    bz_stations[sid]["self_benzina"].append(pval)
                else:
                    bz_stations[sid]["serv_benzina"].append(pval)

    final_list = []
    for sid, s in bz_stations.items():
        prices = {}

        # Günstigster gefundener Preis für Self, teurerer für Servito
        # 1. Diesel
        if s["self_gasolio"]:
            prices["Gasolio (Self)"] = min(s["self_gasolio"])
        elif s["serv_gasolio"]:
            prices["Gasolio (Self)"] = min(s["serv_gasolio"])

        if s["serv_gasolio"]:
            prices["Gasolio (Servito)"] = max(s["serv_gasolio"])

        # 2. Benzin
        if s["self_benzina"]:
            prices["Benzina (Self)"] = min(s["self_benzina"])
        elif s["serv_benzina"]:
            prices["Benzina (Self)"] = min(s["serv_benzina"])

        if s["serv_benzina"]:
            prices["Benzina (Servito)"] = max(s["serv_benzina"])

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

    print(f"Fertige Stationen mit Preisen: {len(final_list)}")

    with open("spritpreise_bz.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
