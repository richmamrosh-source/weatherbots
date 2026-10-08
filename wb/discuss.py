"""WPC discussion sentences that talk about model guidance, from the IEM AFOS archive."""
import datetime as dt
import re

from .common import http_get, log
from .cities import BY_ID, STATE_NAMES

PILS = {"PMDEPD": "WPC Extended Forecast Discussion", "QPFHSD": "WPC Heavy Snow & Icing Discussion",
        "PMDSPD": "WPC Short Range Discussion"}
MODEL_RE = re.compile(r"\b(GFS|ECMWF|ECWMF|EC|EC-AIFS|ECAIFS|AIFS|AIGFS|NAM|CMC|UKMET|UKmet|GEFS|EPS|HREF|RRFS|HRRR)\b")
HDR_RE = re.compile(r"\n(\d{3,4} [AP]M E[SD]T \w{3} \w{3} \d+ \d{4})")


def _products(pil, start, end):
    url = (f"https://mesonet.agron.iastate.edu/cgi-bin/afos/retrieve.py?pil={pil}&sdate={start:%Y-%m-%d}"
           f"&edate={end + dt.timedelta(days=1):%Y-%m-%d}&fmt=text&limit=60&order=asc")
    try:
        t = http_get(url, timeout=90).decode("latin-1")
    except Exception as e:
        log("discussions: fetch failed", pil, e)
        return []
    parts = re.split(r"(?=\n\d{3,4} [AP]M E[SD]T \w{3} \w{3} \d+ \d{4})", t)
    out = []
    for p in parts[1:]:
        m = HDR_RE.match(p)
        if m:
            out.append((m.group(1), re.sub(r"\s+", " ", p)))
    return out


def _issued_utc(h):
    s = h.replace(" EST", "").replace(" EDT", "")
    hm = s.split()[0].zfill(4)
    t = dt.datetime.strptime(hm + " " + " ".join(s.split()[1:]), "%I%M %p %a %b %d %Y")
    return t + dt.timedelta(hours=4 if "EDT" in h else 5)


def quotes(state, start, end, limit=24):
    """Sentences that mention a model AND a place in this storm's area (or the coastal low/system)."""
    places = set()
    for sid in state["stations"]:
        c = BY_ID[sid]
        places.add(c[1])
        places.add(STATE_NAMES.get(c[2], c[2]))
    region_words = {"Northeast", "Mid-Atlantic", "New England", "Great Lakes", "Ohio Valley", "Appalachians", "East Coast",
                    "Plains", "Midwest", "Southeast", "Rockies", "Nor'easter", "Nor'Easter", "nor'easter", "coastal low", "cyclogenesis"}
    region_words |= {state["region"]}
    keys = [w for w in places | region_words if w]
    out, seen = [], set()
    for pil, pname in PILS.items():
        for h, body in _products(pil, start, end):
            for s in re.findall(r"[^.]*\.", body):
                s = s.strip()
                if len(s) < 40 or len(s) > 420 or not MODEL_RE.search(s):
                    continue
                if not any(k in s for k in keys):
                    continue
                if s in seen:
                    continue
                seen.add(s)
                try:
                    t = _issued_utc(h)
                except Exception:
                    continue
                out.append(dict(product=pname, pil=pil, issued_est=h, issued_iso=t.strftime("%Y-%m-%dT%H:%MZ"), text=s))
    out.sort(key=lambda q: q["issued_iso"])
    return out[-limit:]
