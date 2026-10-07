import csv
import json
import urllib.request
import ssl
from datetime import datetime

URL_ANA = "https://www.mimit.gov.it/images/exportCSV/anagrafica_impianti_attivi.csv"
URL_PREZ = "https://www.mimit.gov.it/images/exportCSV/prezzo_alle_8.csv"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {"User-Agent": "Mozilla/5.0"}

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=180, context=ctx) as r:
        return r.read().decode('utf-8', errors='ignore')

def parse_date(s):
    if not s:
        return datetime.min
    for fmt in ("%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            pass
    return datetime.min

def main():
    print("1. Lade Tankstellen...")
    t_ana = fetch(URL_ANA)
    sep_ana = ';' if ';' in t_ana[:500] else '|'
    lines_ana = [l for l in t_ana.splitlines() if l.strip()]
    st_ana = 0
    for idx, l in enumerate(lines_ana[:5]):
        if "idImpianto" in l:
            st_ana = idx
            break

    r_ana = csv.DictReader(lines_ana[st_ana:], delimiter=sep_ana)
    bz = {}

    for row in r_ana:
        row = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k}
        if row.get("Provincia", "").upper() == "BZ":
            sid = row.get("idImpianto")
            if sid:
                bz[sid] = {
                    "id": sid,
                    "name": row.get("Nome Impianto") or row.get("Bandiera") or "Tankstelle",
                    "brand": row.get("Bandiera") or "Freie Tankstelle",
                    "address": row.get("Indirizzo", ""),
                    "city": row.get("Comune", ""),
                    "lat": row.get("Latitudine", "").replace(",", "."),
                    "lon": row.get("Longitudine", "").replace(",", "."),
                    "prices": {},
                    "_dates": {}
                }

    print(f"Südtirol-Stationen: {len(bz)}")

    print("2. Lade Preise...")
    t_prez = fetch(URL_PREZ)
    sep_prez = ';' if ';' in t_prez[:500] else '|'
    lines_prez = [l for l in t_prez.splitlines() if l.strip()]
    st_prez = 0
    for idx, l in enumerate(lines_prez[:5]):
        if "idImpianto" in l:
            st_prez = idx
            break

    r_prez = csv.DictReader(lines_prez[st_prez:], delimiter=sep_prez)
