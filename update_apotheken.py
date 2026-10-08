#!/usr/bin/env python3
"""Holt die Turnusapotheken (Notdienst) der Autonomen Provinz Bozen fuer heute + 13 Tage
und schreibt sie als schlanke JSON-Datei apotheken_turnus.json.
Quelle: Open Data Suedtirol, Webservice der Suedtiroler Turnusapotheken (CC0)
Nur Python-Standardbibliothek. Schlaegt ein Abruf fehl, bleiben die alten Daten fuer den Tag erhalten."""
import json, sys, time, urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

OUT = "apotheken_turnus.json"
DAYS = 14
BASES = ["https://daten.buergernetz.bz.it/services/pharmacy/v1/json",
         "http://daten.buergernetz.bz.it/services/pharmacy/v1/json"]

def fetch(day):
    q = "?date=" + day.strftime("%d.%m.%Y")
    last = None
    for base in BASES:
        for attempt in range(3):
            try:
                req = urllib.request.Request(base + q, headers={"User-Agent": "suedtirolmagazin-apotheken/1.0"})
                with urllib.request.urlopen(req, timeout=40) as r:
                    data = json.loads(r.read().decode("utf-8"))
                if not isinstance(data, list) or not data:
                    raise ValueError("leere oder unerwartete Antwort")
                return data
            except Exception as e:
                last = e
                time.sleep(2 * (attempt + 1))
    raise RuntimeError("Abruf fehlgeschlagen fuer %s: %s" % (day, last))

def hhmm(s):
    return (s or "").strip()

def convert(rows, day):
    iso = day.strftime("%Y-%m-%d")
    out = []
    for r in rows:
        if str(r.get("DATE", ""))[:10] != iso:
            continue                       # Antwort gehoert nicht zum gewuenschten Tag
        if int(r.get("IS_TURN") or 0) != 1:
            continue                       # nur Notdienst-Apotheken
        tt = (r.get("TURN_TIMETABLE") or "").replace(" ", "")
        if "-" not in tt:
            continue
        von, bis = tt.split("-", 1)
        note = (r.get("TURN_NOTES_D") or "").strip()
        out.append({
            "id": r.get("PHAR_ID"),
            "name": (r.get("PHAR_DESC_D") or "").strip(),
            "adresse": (r.get("PHAR_ADRESS_D") or "").strip(),
            "ort": (r.get("GEME_DESC_D") or "").strip(),
            "plz": str(r.get("GEME_ZIP") or "").strip(),
            "tel": (r.get("PHAR_PHONE") or "").strip(),
            "von": hhmm(von), "bis": hhmm(bis),
            "telefonisch": "telefonisch" in note.lower(),
            "hinweis": note,
            "bezirk": (r.get("BEZI_DESC_D") or "").strip(),
        })
    out.sort(key=lambda x: (x["ort"], x["von"], x["name"]))
    return out

def main():
    today = datetime.now(ZoneInfo("Europe/Rome")).date()
    try:
        old = json.load(open(OUT, encoding="utf-8")).get("tage", {})
    except Exception:
        old = {}
    tage, errors = {}, []
    for i in range(DAYS):
        d = today + timedelta(days=i)
        key = d.strftime("%Y-%m-%d")
        try:
            rows = convert(fetch(d), d)
            if not rows:
                raise ValueError("keine Notdienste im Ergebnis")
            tage[key] = rows
        except Exception as e:
            errors.append("%s: %s" % (key, e))
            if key in old:
                tage[key] = old[key]       # letzten bekannten Stand behalten
    if today.strftime("%Y-%m-%d") not in tage:
        print("FEHLER: Keine Daten fuer heute\n" + "\n".join(errors), file=sys.stderr)
        sys.exit(1)
    result = {
        "stand": datetime.now(ZoneInfo("Europe/Rome")).strftime("%Y-%m-%dT%H:%M:%S%z"),
        "quelle": "Autonome Provinz Bozen, Abt. Gesundheit, Open Data (CC0)",
        "tage": tage,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))
    print("OK: %d Tage, %d Eintraege heute" % (len(tage), len(tage[today.strftime('%Y-%m-%d')])))
    for e in errors:
        print("Hinweis:", e)

if __name__ == "__main__":
    main()
