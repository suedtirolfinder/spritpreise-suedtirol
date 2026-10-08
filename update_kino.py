#!/usr/bin/env python3
"""Kinoprogramm Südtirol: liest die Programme mehrerer Kinos und schreibt kino_suedtirol.json.

Quellen (nur öffentliche Programmseiten, jeweils 1-2 Abrufe pro Lauf):
  Odeon (Bruneck), Stella (Brixen)  -> Filme, Genre, Dauer, FSK, Text, Zeiten pro Tag
  Filmclub (Bozen, Meran, ...)      -> Filme, Zeiten pro Tag und Ort, Ticket-Links
  Filmtreff Kaltern                 -> Filme, Dauer, FSK, Zeiten pro Tag
  Cineplexx (Bozen, Algund)         -> Filme, Sprache, Spieltage (ohne Uhrzeiten), Vorschau
  UCI Bozen                         -> nicht lesbar, nur Link

Nur Python-Standardbibliothek. Aufruf:
  python update_kino.py                 # holt die Seiten live
  python update_kino.py --offline DIR   # liest gespeicherte Dateien (zum Testen)
"""
import sys, os, re, json, html, datetime as dt, urllib.request, urllib.robotparser, urllib.parse

UA = "SuedtirolMagazinKino/1.0 (+https://suedtirolmagazin.it; Programmhinweis mit Link zum Kino)"
OUT = "kino_suedtirol.json"
CACHE = "kino_cache.json"   # Rohdaten je Quelle (Rueckfall, falls eine Seite mal ausfaellt)
REPORT = "kino_report.txt"
TODAY = dt.date.today()

CINEMAS = {
    "odeon":     {"name": "ODEON CineCenter", "ort": "Bruneck", "url": "https://www.odeonkino.com/de/programm", "times": True},
    "stella":    {"name": "STELLA Kino", "ort": "Brixen", "url": "https://www.stellakino.com/de/programm", "times": True},
    "filmclub":  {"name": "Filmclub", "ort": "Bozen", "url": "https://www.filmclub.it/de", "times": True},
    "kaltern":   {"name": "Filmtreff Kaltern", "ort": "Kaltern", "url": "https://www.filmtreff-kaltern.it/de/kinoprogramm", "times": True},
    "cineplexx": {"name": "Cineplexx", "ort": "Bozen & Algund", "url": "https://www.cineplexx.bz.it/", "times": False},
    "uci":       {"name": "UCI Cinemas", "ort": "Bozen", "url": "https://ucicinemas.it/cinema/uci-cinemas-bolzano", "times": False, "linkonly": True},
}
# Quellen -> Abruf-URLs (name -> url). "soon" = Vorschau-Seiten
URLS = {
    "odeon": {"now": "https://www.odeonkino.com/de/programm", "soon": "https://www.odeonkino.com/de/vorschau"},
    "stella": {"now": "https://www.stellakino.com/de/programm", "soon": "https://www.stellakino.com/de/vorschau"},
    "filmclub": {"now": "https://www.filmclub.it/de"},
    "kaltern": {"now": "https://www.filmtreff-kaltern.it/de/kinoprogramm"},
    "cineplexx": {"now": "https://www.cineplexx.bz.it/", "soon": "https://www.cineplexx.bz.it/bald-im-kino"},
}
OFFLINE_FILES = {  # nur fuer --offline
    ("odeon", "now"): "odeon_now.html", ("odeon", "soon"): "odeon_soon.html",
    ("stella", "now"): "stella_now.html", ("stella", "soon"): "stella_soon.html",
    ("filmclub", "now"): "filmclub.html", ("kaltern", "now"): "kaltern.html",
    ("cineplexx", "now"): "cx_now.html", ("cineplexx", "soon"): "cx_soon.html",
}

log = []
def say(m):
    print(m); log.append(m)

# ------------------------------------------------------------------ Hilfen
def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()

def unwrap(t):
    """Falls eine 'Seitenquelltext anzeigen'-Datei gespeichert wurde: Viewer-Markup entfernen."""
    if "line-gutter-backdrop" in t[:800]:
        t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return t

def infer_date(d, m):
    """Tag/Monat ohne Jahr -> naechstes passendes Datum (Programm liegt immer in der Naehe von heute)."""
    y = TODAY.year
    try:
        x = dt.date(y, m, d)
    except ValueError:
        return None
    if (TODAY - x).days > 180: x = dt.date(y + 1, m, d)
    if (x - TODAY).days > 185: x = dt.date(y - 1, m, d)
    return x.isoformat()

_robots = {}
def allowed(url):
    p = urllib.parse.urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            req = urllib.request.Request(base + "/robots.txt", headers={"User-Agent": UA})
            raw = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")
            rp.parse(raw.splitlines())
            _robots[base] = rp
        except Exception:
            _robots[base] = None  # robots nicht erreichbar -> nicht blockieren
    rp = _robots[base]
    return True if rp is None else rp.can_fetch(UA, url)

def fetch(src, kind, offline):
    if offline:
        f = os.path.join(offline, OFFLINE_FILES.get((src, kind), ""))
        if not os.path.isfile(f): raise FileNotFoundError(f)
        return unwrap(open(f, encoding="utf-8").read())
    url = URLS[src][kind]
    if not allowed(url): raise RuntimeError("robots.txt verbietet den Abruf")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "de"})
    return urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")

LANGMAP = {"deutsch": "DE", "italienisch": "IT", "englisch": "EN", "de": "DE", "it": "IT", "en": "EN"}
def lang_from_title(t):
    m = re.search(r"\((DE|IT|EN|OV|Original Movie|Original Version)\)\s*$", t, re.I)
    if not m: return t, ""
    k = m.group(1).lower()
    return t[:m.start()].strip(), ("OV" if k.startswith("o") else k.upper())

def nice_title(t):
    t = re.sub(r"\s*\[\d{4}\]", "", t).strip()
    if t.isupper() and len(t) > 3:
        t = t.title()
        t = re.sub(r"\b(Und|Der|Die|Das|Im|Am|Für|Von|Mit|Aus|Zu|Den|Dem|Des|Ein|Eine|Auf|In|Il|Di|La|Le|Dei|Del|Della|Nel)\b",
                   lambda m: m.group(1).lower(), t)
        t = t[0].upper() + t[1:]
        t = re.sub(r"\b(Bts|Met|Mgm|Uci)\b", lambda m: m.group(1).upper(), t)
    return t

# ------------------------------------------------------------------ Odeon / Stella (gleiches System)
def parse_smartline(t, ort):
    m, e = t.find("<main"), t.find("</main>")
    t = re.sub(r"<script.*?</script>", "", t[m:e], flags=re.S)
    out = []
    for p in re.split(r'(?=<div class="col-12 col-md-4 px-2 gsap-onScroll)', t)[1:]:
        if "card-img" not in p: continue
        h = re.search(r"<h3[^>]*>(.*?)</h3>", p, flags=re.S)
        if not h: continue
        raw_title = clean(h.group(1))
        title, tl = lang_from_title(raw_title)
        badges = [clean(x) for x in re.findall(r'<span class="badge[^"]*mb-2 me-2[^"]*">(.*?)</span>', p, flags=re.S)]
        lang = tl or next((LANGMAP[b.lower()] for b in badges if b.lower() in LANGMAP), "")
        if lang == "EN": lang = "OV"
        g = re.search(r"Genre:</span>(.*?)</div>\s*</div>", p, flags=re.S)
        genre = [clean(x) for x in re.findall(r"<span class=\"badge[^>]*>(.*?)</span>", g.group(1), flags=re.S)] if g else []
        def one(label):
            r = re.search(label + r":</span>\s*<span[^>]*>(.*?)</span>", p, flags=re.S)
            return clean(r.group(1)) if r else ""
        dm = re.search(r"(\d+)", one("Laufzeit"))
        d = re.search(r"<strong>Handlung:</strong>(.*?)<span class=\"text-nowrap\"", p, flags=re.S)
        text = clean(d.group(1)) if d else ""
        if text.startswith("igentlich"): text = "E" + text   # Tippfehler der Quelle
        url = (re.search(r'href="([^"]+)" class="card-img"', p) or [0, ""])[1]
        poster = (re.search(r'<img[^>]+\ssrc="(https[^"]+)"', p) or [0, ""])[1]
        trailer = (re.search(r'href="([^"]+)"[^>]*data-trailer', p) or [0, ""])[1]
        heads = []
        for x in re.findall(r"<th[^>]*>(.*?)</th>", p, flags=re.S):
            mm = re.search(r"(\d\d)\.(\d\d)\.", clean(x))
            heads.append(infer_date(int(mm.group(1)), int(mm.group(2))) if mm else None)
        shows = []
        if "<tbody>" in p:
            for row in re.findall(r"<tr>(.*?)</tr>", p.split("<tbody>")[1], flags=re.S):
                for i, c in enumerate(re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S)):
                    c = clean(c)
                    if i < len(heads) and heads[i] and re.fullmatch(r"\d{1,2}:\d\d", c):
                        s = {"ort": ort, "date": heads[i], "time": c.zfill(5)}
                        if s not in shows: shows.append(s)
        out.append({"title": title, "lang": lang, "genre": genre, "dauer": int(dm.group(1)) if dm else 0,
                    "fsk": one("Altersfreigabe"), "text": text, "poster": poster, "trailer": trailer,
                    "url": url, "shows": shows})
    return out

def parse_smartline_soon(t, base_lang=""):
    m, e = t.find("<main"), t.find("</main>")
    t = re.sub(r"<script.*?</script>", "", t[m:e], flags=re.S)
    out = []
    for p in re.split(r'(?=<div class="col mb-5 gsap)', t)[1:]:
        cap = re.search(r'data-caption="([^"]+)"', p)
        if not cap: continue
        title, tl = lang_from_title(html.unescape(cap.group(1)))
        badges = [clean(x) for x in re.findall(r'<span class="badge[^"]*mb-2 me-2[^"]*">(.*?)</span>', p, flags=re.S)]
        lang = tl or next((LANGMAP[b.lower()] for b in badges if b.lower() in LANGMAP), "")
        poster = (re.search(r'<img[^>]+\ssrc="(https[^"]+)"', p) or [0, ""])[1]
        trailer = (re.search(r'href="([^"]+)"[^>]*data-trailer', p) or [0, ""])[1]
        out.append({"title": title, "lang": "OV" if lang == "EN" else lang, "release": "", "poster": poster, "trailer": trailer})
    return out

# ------------------------------------------------------------------ Filmclub
def parse_filmclub(t):
    out = []
    for e in t.split('class="movie-element"')[1:]:
        a = re.search(r'<img alt="([^"]*)"', e)
        if not a: continue
        raw = html.unescape(a.group(1)).strip()
        title, tl = lang_from_title(raw)
        lang = "OV" if tl in ("OV", "EN") else tl
        url = (re.search(r'href="(https://www\.filmclub\.it/de/programm/filme[^"]+)"', e) or [0, ""])[1]
        poster = (re.search(r'<img alt="[^"]*" src="([^"]+)"', e) or [0, ""])[1]
        shows = []
        for ch in e.split('<div class="df schedule">')[1:]:
            md = re.search(r'<div class="inner">\s*[A-Za-z]{2}\s+(\d\d)\.(\d\d)\.\s*</div>', ch)
            ml = re.search(r'class="ac df location mediumFs"><div class="inner">([^<]*)</div>', ch)
            mt = re.search(r'<span class="text">\s*(\d{1,2}:\d\d)\s*</span>', ch)
            if not (md and ml and mt): continue
            d = infer_date(int(md.group(1)), int(md.group(2)))
            mh = re.search(r'<a class="button1" href="([^"]*)"', ch)
            s = {"ort": clean(ml.group(1)), "date": d, "time": mt.group(1).zfill(5)}
            if mh: s["ticket"] = html.unescape(mh.group(1))
            if d and s not in shows: shows.append(s)
        out.append({"title": title, "lang": lang, "genre": [], "dauer": 0, "fsk": "", "text": "",
                    "poster": poster, "trailer": "", "url": url, "shows": shows})
    return out

# ------------------------------------------------------------------ Kaltern
def parse_kaltern(t):
    out = []
    base = "https://www.filmtreff-kaltern.it/"
    for it in re.split(r'(?=<a href="https://www\.filmtreff-kaltern\.it/de/kinoprogramm/e/)', t)[1:]:
        it = it.split("</a>")[0]
        url = re.match(r'<a href="([^"]+)"', it).group(1)
        h = re.search(r'<h3 class="title">(.*?)</h3>', it, flags=re.S)
        if not h: continue
        fsk = re.search(r'class="fsk attr">\s*ab\s+(\d+)\s+Jahren', it)
        dur = re.search(r'class="playingtime attr">\s*(\d+)\s*min', it, re.I)
        if not dur:
            dur = re.search(r'(\d+)\s*Min', clean(it), re.I)
        img = re.search(r'<img[^>]+src="(cache/[^"]+)"', it)
        shows = []
        for d, tm in re.findall(r"[A-Z]{2},\s*(\d\d\.\d\d\.\d{4})\s*\|\s*(\d\d:\d\d)\s*Uhr", clean(it)):
            shows.append({"ort": "Kaltern", "date": dt.datetime.strptime(d, "%d.%m.%Y").date().isoformat(), "time": tm})
        out.append({"title": clean(h.group(1)), "lang": "", "genre": [], "dauer": int(dur.group(1)) if dur else 0,
                    "fsk": (fsk.group(1) + "+") if fsk else "", "text": "", "poster": (base + img.group(1)) if img else "",
                    "trailer": "", "url": url, "shows": shows})
    return out

# ------------------------------------------------------------------ Cineplexx
CX_BASE = "https://www.cineplexx.bz.it"
CX_CIN = {"2360": "Bozen", "5593": "Algund"}
def parse_cineplexx_now(t):
    out = []
    for blk in re.split(r'(?=<div class="inprogrammazione")', t)[1:]:
        head = blk[:blk.find(">") + 1]
        title = html.unescape((re.search(r'data-title="([^"]*)"', head) or [0, ""])[1]).strip()
        if not title: continue
        ver = clean((re.search(r'<div class="versioni">(.*?)</div>', blk, flags=re.S) or [0, ""])[1])
        lang = ""
        v = ver.upper()
        if "ORIGINAL" in v: lang = "OV"
        elif re.search(r"\bDE\b", v): lang = "DE"
        fmt = ", ".join(x for x in ("2D", "3D", "IMAX") if re.search(r"\b" + x + r"\b", v))
        shows = []
        for cid, name in CX_CIN.items():
            val = (re.search(r'data-prog_%s="([^"]*)"' % cid, head) or [0, ""])[1]
            for d in [x for x in val.split("|") if re.fullmatch(r"\d{4}-\d\d-\d\d", x)]:
                shows.append({"ort": name, "date": d, "time": ""})
        img = (re.search(r'<img src="([^"]+)"', blk) or [0, ""])[1]
        if img.startswith("/"): img = CX_BASE + img
        link = (re.search(r'<a href="(/scheda/[^"]+)"', blk) or [0, ""])[1]
        out.append({"title": title, "lang": lang, "format": fmt, "genre": [], "dauer": 0, "fsk": "", "text": "",
                    "poster": img, "trailer": "", "url": (CX_BASE + link) if link else CX_BASE, "shows": shows})
    return out

def parse_cineplexx_soon(t):
    out = []
    for blk in re.split(r'(?=<div class="inprogrammazione")', t)[1:]:
        title = html.unescape((re.search(r'title="([^"]+)"', blk[blk.find('class="titolo"'):]) or [0, ""])[1]).strip()
        rel = re.search(r"Release date:\s*(\d\d)\.(\d\d)\.(\d{4})", clean(blk))
        if not title or not rel: continue
        title, tl = (title.rsplit("|", 1) + [""])[:2] if "|" in title else (title, "")
        lang = tl.strip().upper()
        img = (re.search(r'<img src="([^"]+)"', blk) or [0, ""])[1]
        link = (re.search(r'<a href="(/scheda/[^"]+)"', blk) or [0, ""])[1]
        out.append({"title": title.strip(), "lang": "OV" if "ORIG" in lang else lang[:2],
                    "release": f"{rel.group(3)}-{rel.group(2)}-{rel.group(1)}", "poster": img,
                    "url": (CX_BASE + link) if link else CX_BASE + "/bald-im-kino", "trailer": ""})
    return out

# ------------------------------------------------------------------ Zusammenfuehren
ALIASES = {  # normalisierter Titel -> gemeinsamer Schluessel
    "bibi blocksberg 2 die total verhexte zeitreise": "bibi blocksberg die total verhexte zeitreise",
    "eiserne wildnis": "eiserne wildnis heart of the beast",
    "heart of the beast": "eiserne wildnis heart of the beast",
    "heart of the beast nel profondo selvaggio": "eiserne wildnis heart of the beast",
    "the social": "the social reckoning",
    "the social il prezzo della verita": "the social reckoning",
    "verity": "verity dunkle geheimnisse",
    "dune part three": "dune 3", "dune parte tre": "dune 3",
    "avengers 5 doomsday": "avengers doomsday",
}
def norm(t):
    t = t.lower()
    t = re.sub(r"\[\d{4}\]|\(.*?\)|\b2d\b|\b3d\b", " ", t)
    t = t.replace("ä", "a").replace("ö", "o").replace("ü", "u").replace("è", "e").replace("à", "a").replace("ò", "o").replace("é", "e").replace("ß", "ss")
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return ALIASES.get(t, t)

PREF = ["odeon", "filmclub", "kaltern", "stella", "cineplexx"]   # Titel-/Textquelle in dieser Reihenfolge

WINDOW = 21   # Tage ab heute, die als "laeuft jetzt" zaehlen
def merge(sources):
    films = {}
    horizon = (TODAY + dt.timedelta(days=WINDOW)).isoformat()
    far = {}
    for sid in PREF:
        blk = sources.get(sid)
        if not blk: continue
        for it in blk["films"]:
            key = norm(it["title"])
            f = films.setdefault(key, {"key": key, "title": "", "genre": [], "dauer": 0, "fsk": "", "text": "",
                                      "poster": "", "trailer": "", "langs": [], "shows": [], "links": {}})
            if not f["title"]: f["title"] = nice_title(it["title"])
            for k in ("dauer", "fsk", "text", "poster", "trailer"):
                if not f[k] and it.get(k): f[k] = it[k]
            if not f["genre"] and it.get("genre"): f["genre"] = it["genre"]
            if it.get("lang") and it["lang"] not in f["langs"]: f["langs"].append(it["lang"])
            f["links"][sid] = it.get("url") or CINEMAS[sid]["url"]
            for s in it["shows"]:
                if s["date"] < TODAY.isoformat(): continue
                if s["date"] > horizon:
                    fk = far.setdefault(key, {"title": nice_title(it["title"]), "release": s["date"], "poster": it.get("poster", ""),
                                              "trailer": it.get("trailer", ""), "lang": it.get("lang", ""), "cinema": sid, "url": it.get("url", "")})
                    if s["date"] < fk["release"]: fk["release"] = s["date"]
                    continue
                x = dict(s); x["cinema"] = sid; x["lang"] = it.get("lang", "")
                if it.get("format"): x["format"] = it["format"]
                if not x.get("ticket"): x["ticket"] = it.get("url", "")
                f["shows"].append(x)
    res = []
    for f in films.values():
        if not f["shows"]: continue
        f["shows"].sort(key=lambda s: (s["date"], s["time"] or "99:99", s["cinema"], s["ort"]))
        f["first"] = f["shows"][0]["date"]; f["last"] = f["shows"][-1]["date"]
        res.append(f)
    res.sort(key=lambda f: (-len({s["cinema"] + s["ort"] for s in f["shows"]}), f["title"].lower()))
    running = {f["key"] for f in res}
    farlist = [dict(v, key=k) for k, v in far.items() if k not in running]
    return res, farlist

def merge_soon(sources, farlist=()):
    soon = {}
    for it in farlist:
        k = norm(it["title"])
        soon[k] = {"title": it["title"], "release": it["release"], "poster": it["poster"], "trailer": it["trailer"],
                   "langs": [it["lang"]] if it["lang"] else [], "cinemas": [it["cinema"]],
                   "links": {it["cinema"]: it["url"] or CINEMAS[it["cinema"]]["url"]}}
    for sid in ("cineplexx", "odeon", "stella"):
        blk = sources.get(sid)
        if not blk: continue
        for it in blk.get("soon", []):
            k = norm(it["title"])
            s = soon.setdefault(k, {"title": nice_title(it["title"]), "release": "", "poster": "", "trailer": "", "langs": [], "cinemas": [], "links": {}})
            if it.get("release") and (not s["release"] or it["release"] < s["release"]): s["release"] = it["release"]
            for kk in ("poster", "trailer"):
                if not s[kk] and it.get(kk): s[kk] = it[kk]
            if it.get("lang") and it["lang"] not in s["langs"]: s["langs"].append(it["lang"])
            if sid not in s["cinemas"]: s["cinemas"].append(sid)
            s["links"][sid] = it.get("url") or CINEMAS[sid]["url"]
    res = [s for s in soon.values() if not s["release"] or s["release"] >= TODAY.isoformat()]
    res.sort(key=lambda s: (s["release"] or "9999", s["title"]))
    return res

# ------------------------------------------------------------------ Hauptprogramm
def main():
    offline = None
    if "--offline" in sys.argv: offline = sys.argv[sys.argv.index("--offline") + 1]
    try:
        old = json.load(open(CACHE, encoding="utf-8"))
    except Exception:
        old = {}
    old_src = old.get("sources", {})
    sources = {}
    for sid in ("odeon", "stella", "filmclub", "kaltern", "cineplexx"):
        blk = {"ok": False, "films": [], "soon": [], "fetched": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds") + "Z"}
        try:
            t = fetch(sid, "now", offline)
            if sid in ("odeon", "stella"): blk["films"] = parse_smartline(t, CINEMAS[sid]["ort"])
            elif sid == "filmclub":
                blk["films"] = parse_filmclub(t)
                if len(blk["films"]) >= 16: say("filmclub: 16+ Filme, Seite blaettert vermutlich weiter (nur Seite 1 gelesen)")
            elif sid == "kaltern": blk["films"] = parse_kaltern(t)
            elif sid == "cineplexx": blk["films"] = parse_cineplexx_now(t)
            if not blk["films"]: raise RuntimeError("keine Filme erkannt (Seitenaufbau geaendert?)")
            blk["ok"] = True
            if "soon" in URLS.get(sid, {}):
                try:
                    ts = fetch(sid, "soon", offline)
                    blk["soon"] = parse_cineplexx_soon(ts) if sid == "cineplexx" else parse_smartline_soon(ts)
                except Exception as e:
                    say(f"{sid}: Vorschau nicht gelesen ({e})")
            n = sum(len(f["shows"]) for f in blk["films"])
            say(f"{sid}: OK, {len(blk['films'])} Filme, {n} Vorstellungen/Tage, {len(blk['soon'])} Vorschau")
        except Exception as e:
            say(f"{sid}: FEHLER ({e})")
            if old_src.get(sid, {}).get("films"):
                blk = dict(old_src[sid]); blk["ok"] = False
                blk["stale"] = True
                say(f"{sid}: verwende Daten vom letzten erfolgreichen Lauf ({blk.get('fetched')})")
        sources[sid] = blk

    ok = [s for s in sources.values() if s["ok"]]
    if not ok:
        say("Alle Quellen fehlgeschlagen, bestehende Datei bleibt unveraendert.")
        open(REPORT, "w", encoding="utf-8").write("\n".join(log) + "\n"); return 1
    films, farlist = merge(sources)
    soon = merge_soon(sources, farlist)
    # Vorschau-Filme, die inzwischen laufen, entfernen
    running = {f["key"] for f in films}
    soon = [s for s in soon if norm(s["title"]) not in running]
    out = {
        "generated": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds") + "Z",
        "today": TODAY.isoformat(),
        "cinemas": {k: {kk: vv for kk, vv in v.items()} for k, v in CINEMAS.items()},
        "status": {k: {"ok": v["ok"], "stale": v.get("stale", False), "fetched": v.get("fetched")} for k, v in sources.items()},
        "films": films, "soon": soon,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    json.dump({"sources": sources}, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    say(f"Gesamt: {len(films)} Filme, {sum(len(f['shows']) for f in films)} Eintraege, {len(soon)} in der Vorschau. Datei {os.path.getsize(OUT)//1024} KB")
    open(REPORT, "w", encoding="utf-8").write("\n".join(log) + "\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
