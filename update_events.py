#!/usr/bin/env python3
"""Holt Veranstaltungen fuer Suedtirol aus dem Open Data Hub (Tourism API, Endpunkt /v1/Event),
fuer heute + 13 Tage, und schreibt:
  events_south_tyrol.json  Termine pro Tag (ohne Dauerausstellungen) fuer Startseite / Event-Seite
  events_dauer.json        Dauerausstellungen & Co. (laufen >14 Tage), nur einmal je Eintrag
  events_report.txt        Auswertung: Anzahl pro Ort, Lizenzen, Quellen, Dauerausstellungen (zum Pruefen)
Nur Python-Standardbibliothek. Bei einem Fehler bleiben die alten Dateien unveraendert."""
import json, sys, time, urllib.request, urllib.parse
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

API = "https://tourism.api.opendatahub.com/v1/Event"
DAYS = 14
PAGESIZE = 200
MAX_PAGES = 30
OUT = "events_south_tyrol.json"
OUT_DAUER = "events_dauer.json"
REPORT = "events_report.txt"
ORTE = {"Bozen": ("bozen", "bolzano"), "Meran": ("meran", "merano"),
        "Brixen": ("brixen", "bressanone"), "Bruneck": ("bruneck", "brunico")}

def get(url):
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "suedtirolmagazin-events/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("Abruf fehlgeschlagen: %s (%s)" % (url, last))

def tr(d, *langs):
    """Text aus einem {de:..,it:..,en:..}-Objekt, bevorzugt Deutsch."""
    if not isinstance(d, dict):
        return ""
    for l in langs or ("de", "it", "en"):
        v = d.get(l)
        if v:
            return str(v).strip()
    for v in d.values():
        if v:
            return str(v).strip()
    return ""

def title_of(e):
    det = e.get("Detail") or {}
    for l in ("de", "it", "en"):
        t = ((det.get(l) or {}).get("Title") or "").strip()
        if t:
            return t
    for v in det.values():
        t = ((v or {}).get("Title") or "").strip()
        if t:
            return t
    return ""

def place_of(e):
    li = e.get("LocationInfo") or {}
    mun = tr((li.get("MunicipalityInfo") or {}).get("Name"))
    if not mun:
        ci = e.get("ContactInfos") or {}
        for l in ("de", "it", "en"):
            c = ((ci.get(l) or {}).get("City") or "").strip()
            if c:
                mun = c
                break
    return mun, tr((li.get("DistrictInfo") or {}).get("Name")), tr((li.get("TvInfo") or {}).get("Name"))

def contact(e):
    ci = e.get("ContactInfos") or {}
    for l in ("de", "it", "en"):
        c = ci.get(l) or {}
        if c.get("Address") or c.get("Url") or c.get("City"):
            return (str(c.get("Address") or "").strip(), str(c.get("ZipCode") or "").strip(), str(c.get("Url") or "").strip())
    return ("", "", "")

def day(s):
    return str(s or "")[:10]

def hm(s):
    s = str(s or "")
    if "T" in s:
        s = s.split("T", 1)[1]
    return s[:5] if len(s) >= 5 and s[2] == ":" else ""

def occurrences(e, first, last):
    """Liefert (datum, von, bis) fuer jeden Tag im Fenster. Nutzt EventDate, sonst DateBegin/DateEnd."""
    res = []
    eds = e.get("EventDate") or []
    for ed in eds:
        d = day(ed.get("From") or ed.get("Begin"))
        if not d:
            continue
        v = hm(ed.get("Begin")) or hm(ed.get("From"))
        b = hm(ed.get("End")) or hm(ed.get("To"))
        # mehrtaegige Eintraege (From..To) auf Einzeltage verteilen
        d2 = day(ed.get("To")) or d
        cur = datetime.strptime(d, "%Y-%m-%d").date()
        end = datetime.strptime(d2, "%Y-%m-%d").date()
        n = 0
        while cur <= end and n < 62:
            if first <= cur <= last:
                res.append((cur.isoformat(), v, b))
            cur += timedelta(days=1)
            n += 1
    if not res and not eds:
        d1, d2 = day(e.get("DateBegin")), day(e.get("DateEnd")) or day(e.get("DateBegin"))
        if d1:
            cur = datetime.strptime(d1, "%Y-%m-%d").date()
            end = datetime.strptime(d2, "%Y-%m-%d").date()
            n = 0
            while cur <= end and n < 62:
                if first <= cur <= last:
                    res.append((cur.isoformat(), hm(e.get("DateBegin")), hm(e.get("DateEnd"))))
                cur += timedelta(days=1)
                n += 1
    return res

def fetch_all(first, last):
    params = {"pagenumber": 1, "pagesize": PAGESIZE, "begindate": first.isoformat(), "enddate": last.isoformat(),
              "active": "true", "language": "de", "removenullvalues": "true"}
    url = API + "?" + urllib.parse.urlencode(params)
    items, pages, total = [], 0, None
    while url and pages < MAX_PAGES:
        data = get(url)
        total = data.get("TotalResults", total)
        items.extend(data.get("Items") or [])
        url = data.get("NextPage")
        pages += 1
    return items, total, pages

def main():
    today = datetime.now(ZoneInfo("Europe/Rome")).date()
    first, last = today, today + timedelta(days=DAYS - 1)
    items, total, pages = fetch_all(first, last)
    if not items:
        print("FEHLER: keine Veranstaltungen erhalten", file=sys.stderr)
        sys.exit(1)

    seen, by_day, dauer_list = set(), {}, []
    lic, src, per_place, per_place_real = Counter(), Counter(), Counter(), Counter()
    no_mun = long_running = no_title = kept = 0
    other_mun = Counter()
    for e in items:
        eid = e.get("Id")
        if eid in seen:
            continue
        seen.add(eid)
        title = title_of(e)
        if not title:
            no_title += 1
            continue
        mun, dist, tv = place_of(e)
        if not mun:
            no_mun += 1
        adr, plz, url = contact(e)
        lic[str((e.get("LicenseInfo") or {}).get("License") or "?")] += 1
        src[str(e.get("Source") or "?")] += 1
        # Dauerausstellung = ein einzelner Terminblock laeuft laenger als 14 Tage
        def dd(x):
            try:
                return datetime.strptime(day(x), "%Y-%m-%d").date()
            except Exception:
                return None
        long_from = long_to = None
        eds = e.get("EventDate") or []
        for ed in eds:
            f, t = dd(ed.get("From") or ed.get("Begin")), dd(ed.get("To"))
            if f and t and (t - f).days > 14:
                long_from, long_to = f, t
                break
        if not eds:
            f, t = dd(e.get("DateBegin")), dd(e.get("DateEnd"))
            if f and t and (t - f).days > 14:
                long_from, long_to = f, t
        dauer = long_from is not None
        if dauer:
            long_running += 1
            if long_to < first or long_from > last:
                continue
        occ = [] if dauer else occurrences(e, first, last)
        if not occ and not dauer:
            continue
        kept += 1
        low = (mun or "").lower()
        hit = False
        for name, keys in ORTE.items():
            if any(k in low for k in keys):
                per_place[name] += 1
                hit = True
        if not hit and mun:
            other_mun[mun] += 1
        gps = (e.get("GpsInfo") or [{}])[0] if isinstance(e.get("GpsInfo"), list) and e.get("GpsInfo") else {}
        def rnd(x):
            try:
                return round(float(x), 5)
            except Exception:
                return None
        rec = {"id": eid, "titel": title, "ort": mun, "bezirk": dist,
               "adresse": ((adr + ", " if adr else "") + (plz + " " if plz else "") + mun).strip(", "),
               "url": url, "lat": rnd(gps.get("Latitude")), "lng": rnd(gps.get("Longitude"))}
        if dauer:
            rec["ab"] = long_from.isoformat()
            rec["bis_tag"] = long_to.isoformat()
            dauer_list.append(rec)
            continue
        for name, keys in ORTE.items():
            if any(k in low for k in keys):
                per_place_real[name] += 1
        for d, v, b in occ:
            by_day.setdefault(d, []).append(dict(rec, von=v, bis=b))
    for d in by_day:
        by_day[d].sort(key=lambda x: (x["von"] or "99:99", x["titel"]))

    result = {"stand": datetime.now(ZoneInfo("Europe/Rome")).strftime("%Y-%m-%dT%H:%M:%S%z"),
              "quelle": "Open Data Hub Suedtirol, Tourism API (Event)", "tage": dict(sorted(by_day.items()))}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))
    dauer_list.sort(key=lambda x: (x["ort"], x["titel"]))
    with open(OUT_DAUER, "w", encoding="utf-8") as f:
        json.dump({"stand": result["stand"], "quelle": result["quelle"], "liste": dauer_list}, f, ensure_ascii=False, separators=(",", ":"))

    sample = items[0] if items else {}
    lines = ["EVENT-AUSWERTUNG  Stand %s" % result["stand"],
             "Zeitraum: %s bis %s" % (first, last),
             "Gemeldet von der API: %s, geladen: %d (Seiten: %d)" % (total, len(items), pages),
             "Eindeutige Veranstaltungen mit Termin im Zeitraum: %d" % kept,
             "Ohne Titel: %d, ohne Gemeinde: %d, Dauerausstellungen (>14 Tage): %d" % (no_title, no_mun, long_running),
             "", "Veranstaltungen pro Ort (nur Termine im Zeitraum):"]
    for name in ORTE:
        lines.append("  %-8s %d  (davon echte Termine ohne Dauerausstellungen: %d)" % (name, per_place[name], per_place_real[name]))
    lines += ["", "Lizenzen: " + json.dumps(dict(lic), ensure_ascii=False),
              "Quellen:  " + json.dumps(dict(src), ensure_ascii=False),
              "", "Termine pro Tag (ohne Dauerausstellungen):"]
    for d, v in sorted(by_day.items()):
        lines.append("  %s  %d" % (d, len(v)))
    lines += ["", "Haeufigste weitere Gemeinden: " + ", ".join("%s (%d)" % kv for kv in other_mun.most_common(15)),
              "", "Felder des ersten Eintrags: " + ", ".join(sorted(sample.keys())),
              "Beispiel EventDate: " + json.dumps((sample.get("EventDate") or [None])[0], ensure_ascii=False)[:300]]
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
