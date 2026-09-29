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

def get_text(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=180, context=ctx) as resp:
        return resp.read().decode('utf-8', errors='ignore')

def main():
    print("1. Lade Tankstellen...")
    raw_ana = get_text(URL_ANAGRAFICA)
    bz_stations = {}

    for line in raw_ana.splitlines():
        line = line.strip()
        if not line or "idImpianto" in line:
            continue
        
        # Trennzeichen bestimmen (entweder | oder ;)
        parts = line.split('|') if '|' in line else line.split(';')
        if len(parts) < 9:
            continue

        # Format: idImpianto|Gestore|Bandiera|Tipo Impianto|Nome Impianto|Indirizzo|Comune|Provincia|Latitudine|Longitudine
        sid = parts[0].strip()
        prov = parts[7].strip().upper()

        if prov == "BZ" and sid:
            bandiera = parts[2].strip() or "Freie Tankstelle"
            nome = parts[4].strip() or bandiera
            indirizzo = parts[5].strip()
            comune = parts[6].strip()
            lat = parts[8].strip().replace(",", ".")
            lon = parts[9].strip().replace(",", ".") if len(parts) > 9 else ""

            bz_stations[sid] = {
                "id": sid,
                "name": nome,
                "brand": bandiera,
                "address": indirizzo,
                "city": comune,
                "lat": lat,
                "lon": lon,
                "prices_diesel": [],
                "prices_benzin": []
            }

    print(f"Stationen in Südtirol: {len(bz_stations)}")

    print("2. Lade Preise...")
    raw_prez = get_text(URL_PREZZI)

    # Blacklist für Additive & 100 Oktan
    BLACKLIST = ["100", "plus", "optima", "v-power", "racing", "additiv", "supreme", "excellium", "special", "hi-q"]

    for line in raw_prez.splitlines():
        line = line.strip()
        if not line or "idImpianto" in line:
            continue

        parts = line.split('|') if '|' in line else line.split(';')
        if len(parts) < 3:
            continue

        # Format: idImpianto|descCarburante|prezzo|isSelf|dtComu
        sid = parts[0].strip()
        if sid in bz_stations:
            fuel = parts[1].strip().lower()
            price_str = parts[2].strip().replace(",", ".")

            if any(b in fuel for b in BLACKLIST):
                continue

            try:
                pval = float(price_str)
            except ValueError:
                continue

            # Realistische Preisgrenzen (1.20 € bis 2.60 €)
            if not (1.20 <= pval <= 2.60):
                continue

            if "diesel" in fuel or "gasolio" in fuel:
                bz_stations[sid]["prices_diesel"].append(pval)
            elif "benzina" in fuel or "senza piombo" in fuel:
                bz_stations[sid]["prices_benzin"].append(pval)

    final_list = []
    for sid, s in bz_stations.items():
        prices = {}

        # DIESEL: Niedrigster gemeldeter Preis = Self, höchster = Servito
        if s["prices_diesel"]:
            d_sorted = sorted(s["prices_diesel"])
            prices["Gasolio (Self)"] = d_sorted[0]
            if len(d_sorted) > 1 and d_sorted[-1] > d_sorted[0]:
                prices["Gasolio (Servito)"] = d_sorted[-1]
            else:
                prices["Gasolio (Servito)"] = d_sorted[0]

        # BENZIN: Niedrigster gemeldeter Preis = Self, höchster = Servito
        if s["prices_benzin"]:
            b_sorted = sorted(s["prices_benzin"])
            prices["Benzina (Self)"] = b_sorted[0]
            if len(b_sorted) > 1 and b_sorted[-1] > b_sorted[0]:
                prices["Benzina (Servito)"] = b_sorted[-1]
            else:
                prices["Benzina (Servito)"] = b_sorted[0]

        if prices:
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
