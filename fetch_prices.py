import csv
import json
import io
import urllib.request

# Offizielle MIMIT Open Data CSV-URLs
URL_ANAGRAFICA = "https://www.mimit.gov.it/images/exportCSV/anagrafica_impianti_attivi.csv"
URL_PREZZI = "https://www.mimit.gov.it/images/exportCSV/prezzo_alle_8.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def download_csv(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as response:
        content = response.read().decode('utf-8', errors='ignore')
    return list(csv.reader(io.StringIO(content), delimiter=';'))

def process_data():
    print("1. Lade Tankstellen-Stammdaten herunter...")
    anagrafica_rows = download_csv(URL_ANAGRAFICA)
    
    bz_stations = {}
    for row in anagrafica_rows:
        # idImpianto;Gestore;Bandiera;Tipo Impianto;Nome Impianto;Indirizzo;Comune;Provincia;Latitudine;Longitudine
        if len(row) >= 8 and row[7].strip().upper() == "BZ":
            station_id = row[0].strip()
            bz_stations[station_id] = {
                "id": station_id,
                "name": row[4].strip() or row[2].strip(),
                "brand": row[2].strip(),
                "address": row[5].strip(),
                "city": row[6].strip(),
                "lat": row[8].strip() if len(row) > 8 else "",
                "lon": row[9].strip() if len(row) > 9 else "",
                "prices": {}
            }
            
    print(f"{len(bz_stations)} Tankstellen in Südtirol (BZ) erfasst.")

    print("2. Lade Preisdaten herunter...")
    prezzi_rows = download_csv(URL_PREZZI)
    
    for row in prezzi_rows:
        # idImpianto;descCarburante;prezzo;isSelf;dtComu
        if len(row) >= 4:
            station_id = row[0].strip()
            if station_id in bz_stations:
                fuel_type = row[1].strip()
                try:
                    price = float(row[2].strip().replace(",", "."))
                except ValueError:
                    continue
                is_self = row[3].strip() == "1"
                
                fuel_key = f"{fuel_type} ({'Self' if is_self else 'Servito'})"
                bz_stations[station_id]["prices"][fuel_key] = price

    # Nur Tankstellen behalten, die auch gültige Preise gemeldet haben
    active_stations = [s for s in bz_stations.values() if len(s["prices"]) > 0]

    with open("spritpreise_bz.json", "w", encoding="utf-8") as f:
        json.dump(active_stations, f, ensure_ascii=False, indent=2)
        
    print(f"Fertig! {len(active_stations)} aktive Tankstellen mit Preisen gespeichert.")

if __name__ == "__main__":
    process_data()
