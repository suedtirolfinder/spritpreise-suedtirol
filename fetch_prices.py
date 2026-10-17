import csv
import json
import urllib.request
import ssl
import time
from datetime import datetime, timezone

URL_ANA = "https://www.mimit.gov.it/images/exportCSV/anagrafica_impianti_attivi.csv"
URL_PREZ = "https://www.mimit.gov.it/images/exportCSV/prezzo_alle_8.csv"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {"User-Agent": "Mozilla/5.0"}

def fetch(url):
    last = None
    for versuch in range(1, 4):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=180, context=ctx) as r:
                return r.read().decode('utf-8', errors='ignore')
        except Exception as e:  # Netzwerkfehler, Zeitüberschreitung
            last = e
            print(f"  Versuch {versuch} fehlgeschlagen: {e}")
            time.sleep(10 * versuch)
    raise SystemExit(f"Abruf fehlgeschlagen: {url} ({last})")

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

    # Spalten: idImpianto;descCarburante;prezzo;isSelf;dtComu
    n_rows = 0
    for row in r_prez:
        row = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k}
        sid = row.get("idImpianto")
        if sid not in bz:
            continue
        n_rows += 1
        desc = row.get("descCarburante", "").lower()
        if "alpino" in desc:
            sorte = "Alpino"
        elif desc.startswith("benzina"):
            sorte = "Benzina"
        elif desc.startswith("gasolio"):
            sorte = "Gasolio"
        else:
            continue  # Gas, Methan, AdBlue usw. brauchen wir nicht
        try:
            preis = float(row.get("prezzo", "").replace(",", "."))
        except ValueError:
            continue
        if not 0.5 <= preis <= 4.0:
            continue  # offensichtlich fehlerhafter Wert
        art = "Self" if row.get("isSelf", "") in ("1", "true", "True") else "Servito"
        key = f"{sorte} ({art})"
        datum = parse_date(row.get("dtComu", ""))
        if key not in bz[sid]["_dates"] or datum >= bz[sid]["_dates"][key]:
            bz[sid]["prices"][key] = round(preis, 3)
            bz[sid]["_dates"][key] = datum

    print(f"Preiszeilen für Südtirol: {n_rows}")

    out = []
    for st in bz.values():
        if not st["prices"]:
            continue
        st.pop("_dates", None)
        out.append(st)
    out.sort(key=lambda x: (x["city"], x["name"]))

    # Schutz: lieber die alten Daten behalten als eine fast leere Datei speichern
    if len(out) < 50:
        raise SystemExit(f"Nur {len(out)} Stationen mit Preisen, das ist zu wenig. Datei bleibt unverändert.")

    with open("spritpreise_bz.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    with open("spritpreise_stand.json", "w", encoding="utf-8") as f:
        json.dump({"stand": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "stationen": len(out)}, f, indent=2)
    print(f"Fertig: {len(out)} Stationen gespeichert.")


if __name__ == "__main__":
    main()
