import csv
import json
import io
import urllib.request

URL_ANAGRAFICA = "https://www.mimit.gov.it/images/exportCSV/anagrafica_impianti_attivi.csv"
URL_PREZZI = "https://www.mimit.gov.it/images/exportCSV/prezzo_alle_8.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_csv_dict_reader(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as response:
        content = response.read().decode('utf-8', errors='ignore')
    
    # Eventuelle Leerzeilen oder Einleitungszeilen überspringen, bis der echte Header kommt
    lines = content.splitlines()
    header_index = 0
    for idx, line in enumerate(lines[:10]):
        if "idImpianto" in line:
            header_index = idx
            break
            
    clean_csv_content = "\n".join(lines[header_index:])
    return list(csv.DictReader(io.StringIO(clean_csv_content), delimiter=';'))

def process_data():
    print("1. Lade Tankstellen-Stammdaten herunter...")
    anagrafica_rows = get_csv_dict_reader(URL_ANAGRAFICA)
    
    bz_stations = {}
    for row in anagrafica_rows:
        # Sicherer Zugriff auf Spaltennamen (ignoriert Groß/Kleinschreibung und Leerzeichen)
        clean_row = {k.strip(): v.strip() for k, v in row.items() if k}
        
        provincia = clean_row.get("Provincia", "").upper()
        if provincia == "BZ":
            station_id = clean_row.get("idImpianto")
            if station_id:
                bz_stations[station_id] = {
                    "id": station_id,
                    "name": clean_row.get("Nome Impianto") or clean_row.get("Bandiera") or "Tankstelle",
                    "brand": clean_row.get("Bandiera") or "Freie Tankstelle",
                    "address": clean_row.get("Indirizzo", ""),
                    "city": clean_row.get("Comune", ""),
                    "lat": clean_row.get("Latitudine", ""),
                    "lon": clean_row.get("Longitudine", ""),
                    "prices": {}
                }
            
    print(f"{len(bz_stations)} Tankstellen in Südtirol (BZ) gefunden.")

    print("2. Lade Preisdaten herunter...")
    prezzi_rows = get_csv_dict_reader(URL_PREZZI)
    
    for row in prezzi_rows:
        clean_row = {k.strip(): v.strip() for k, v in row.items() if k}
        station_id = clean_row.get("idImpianto")
        
        if station_id and station_id in bz_stations:
            fuel_desc = clean_row.get("descCarburante", "").strip()
            price_str = clean_row.get("prezzo", "").replace(",", ".").strip()
            is_self = clean_row.get("isSelf", "0").strip() == "1"
            
            try:
                price = float(price_str)
                mode_str = "Self" if is_self else "Servito"
                fuel_key = f"{fuel_desc} ({mode_str})"
                bz_stations[station_id]["prices"][fuel_key] = price
            except ValueError:
                continue

    output_list = list(bz_stations.values())
    with open("spritpreise_bz.json", "w", encoding="utf-8") as f:
        json.dump(output_list, f, ensure_ascii=False, indent=2)
        
    print(f"Erfolgreich gespeichert! Gesamt: {len(output_list)} Tankstellen.")

if __name__ == "__main__":
    process_data()
