"""Shared helpers: paths, time formatting, HTTP, geometry."""
import datetime as dt
import json
import math
import os
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "work")
SITE = os.path.join(ROOT, "site")
DATA = os.path.join(SITE, "data")
STORMS = os.path.join(DATA, "storms")
UA = {"User-Agent": "weatherbots/1.0 (github.com/richmamrosh-source/weatherbots)"}


def config():
    with open(os.path.join(ROOT, "config.json")) as f:
        return json.load(f)


def utcnow():
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def iso(t):
    return t.strftime("%Y-%m-%dT%HZ")


def parse_iso(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%HZ")


def ymdh(t):
    return t.strftime("%Y%m%d%H")


def http_get(url, rng=None, tries=6, timeout=120):
    last = None
    for k in range(tries):
        try:
            h = dict(UA)
            if rng:
                h["Range"] = f"bytes={rng[0]}-{rng[1]}"
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                raise
            last = e
            if e.code in (429, 503):  # throttled: back off harder
                time.sleep(5 * (k + 1))
        except Exception as e:  # network hiccup
            last = e
        time.sleep(2 * (k + 1))
    raise last


def http_exists(url, tries=5):
    """True if the URL exists. Retries throttling and network errors; only a 403/404 counts as 'not there'."""
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA, method="HEAD")
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status == 200
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return False
        except Exception:
            pass
        time.sleep(4 * (k + 1))
    return False


def hav(la1, lo1, la2, lo2):
    p1, p2 = math.radians(la1), math.radians(la2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(min(1.0, a)))


def bearing_word(la1, lo1, la2, lo2):
    """Compass direction of point 2 relative to point 1 (8-point)."""
    y = math.sin(math.radians(lo2 - lo1)) * math.cos(math.radians(la2))
    x = math.cos(math.radians(la1)) * math.sin(math.radians(la2)) - math.sin(math.radians(la1)) * math.cos(math.radians(la2)) * math.cos(math.radians(lo2 - lo1))
    b = (math.degrees(math.atan2(y, x)) + 360) % 360
    return ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"][int((b + 22.5) // 45) % 8]


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)


def write_json(path, obj, compact=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        if compact:
            json.dump(obj, f, separators=(",", ":"))
        else:
            json.dump(obj, f, indent=1)
    os.replace(tmp, path)


def log(*a):
    print(f"[{utcnow():%H:%M:%S}]", *a, flush=True)
