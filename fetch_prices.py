import csv
import json
import urllib.request
import ssl
from datetime import datetime

# Datenquelle: Ministero delle Imprese e del Made in Italy (MIMIT)
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
    """Parst das MIMIT Datumsformat ('YYYY-MM-DD HH:MM:SS' oder 'DD/MM/YYYY HH:MM:SS')"""
    if not date_str:
        return datetime.min
    for fmt in ("%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            pass
    return datetime.min

def main():
    print("==================================================")
    print(" Datenquelle: MIMIT (Ministero delle Imprese e del Made in Italy)")
    print("==================================================")
    print("1. Lade Tankstellen (Anagrafica)...")
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
                    "name": row.get
