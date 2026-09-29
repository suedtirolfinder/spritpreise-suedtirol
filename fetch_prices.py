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

def get_csv_lines(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=180, context=ctx) as resp:
        content = resp.read().decode('utf-8', errors='ignore')
    return [line.strip() for line in content.splitlines() if line.strip()]

def main():
    print("1. Lade Tankstellen-Stammdaten...")
    anagrafica_lines = get_csv_lines(URL_ANAGRAFICA)
    
    start_idx = 0
    delimiter = '|'
    for idx, line in enumerate(anagrafica_lines[:5]):
        if "idImpianto" in line:
            start_idx = idx
            delimiter = ';' if ';' in line else '|'
            break

    reader = csv.DictReader(anagrafica_lines[start_idx:], delimiter=delimiter)
    
    bz_stations = {}
    for row in reader:
        clean = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k}
        if clean.get("Provincia", "").upper() == "BZ":
            s_id = clean.get("idImpianto")
            if s_id:
                bz_stations[s_id] = {
                    "id": s_id,
                    "name": clean.get("Nome Impianto") or clean.get("Bandiera") or "Tankstelle",
                    "brand": clean.get("Bandiera") or "Freie Tankstelle",
                    "address": clean.get("Indirizzo", ""),
                    "city": clean.get("Comune", ""),
                    "lat": clean.get("Latitudine", "").replace(",", "."),
                    "lon": clean.get("Longitudine", "").replace(",", "."),
                    "prices": {}
                }

    print(f"Gefundene Stationen in Südtirol: {len(bz_stations)}")

    print("2. Lade aktuelle Preise...")
    prezzi_lines = get_csv_lines(URL_PREZZI)
    
    start_idx_p = 0
    p_delimiter = '|'
    for idx, line in enumerate(prezzi_lines[:5]):
        if "idImpianto" in line:
            start_idx_p = idx
            p_delimiter = ';' if ';' in line else '|'
            break

    p_reader = csv.DictReader(prezzi_lines[start_idx_p:], delimiter=p_delimiter)
    for row in p_reader:
        clean = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k}
        s_id = clean.get("idImpianto")
        
        if s_id in bz_stations:
            fuel = clean.get("descCarburante", "").strip()
            price_str = clean.get("prezzo", "").replace(",", ".").strip()
            
            # Robuste Self/Servito Erkennung: '1', 'true', 's' bedeutet Self-Service
            is_self_val = str(clean.get("isSelf", "0")).strip().lower()
            is_self = is_self_val in ["1", "true", "s", "si", "self"]

            try:
                price_val = float(price_str)
                # Unplausible Ausreißer oder Testpreise unter 1.00 € ignorieren
                if price_val < 1.0:
                    continue

                mode_key = "Self" if is_self else "Servito"
                full_key = f"{fuel} ({mode_key})"

                # Falls mehrere Preise für dieselbe Sorte gemeldet sind (z.B. Normal vs Additiv),
                # speichern wir für Self-Service immer den GÜNSTIGEREN Preis!
                if full_key not in bz_stations[s_id]["prices"]:
                    bz_stations[s_id]["prices"][full_key] = price_val
                else:
                    if is_self:
                        bz_stations[s_id]["prices"][full_key] = min(bz_stations[s_id]["prices"][full_key], price_val)
                    else:
                        bz_stations[s_id]["prices"][full_key] = price_val
            except ValueError:
                continue

    output = [s for s in bz_stations.values() if len(s["prices"]) > 0]
    print(f"Ergebnis: {len(output)} Stationen mit gültigen Preisen.")

    with open("spritpreise_bz.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
