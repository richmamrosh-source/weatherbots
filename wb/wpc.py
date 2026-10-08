"""Watch WPC's probabilistic winter precipitation forecast (2.5 km, 24-h snowfall probabilities, Days 1-3).

A 24-h window is "significant" when the area with P(snow >= threshold) >= prob_pct exceeds min_area_km2.
Contiguous significant windows (in time and space) become one storm candidate.
"""
import datetime as dt
import os
import re
import tempfile

import numpy as np
import pygrib

from .common import WORK, http_get, log, hav, iso
from .cities import CITIES, region_name

BASE = "https://ftp-wpc.ncep.noaa.gov/pwpf/conus_2.5km/2.5kmpwpf_24hr/"


def latest_init(thresh=8):
    html = http_get(BASE).decode("latin-1")
    inits = sorted(set(re.findall(rf"psnow24_ge{thresh}_(\d{{10}})f072\.grb", html)))
    return inits[-1] if inits else None


def _read(url):
    blob = http_get(url)
    with tempfile.NamedTemporaryFile(suffix=".grb", delete=False) as f:
        f.write(blob)
        p = f.name
    try:
        g = pygrib.open(p)
        m = g.message(1)
        v = np.ma.filled(m.values, np.nan).astype("f4")
        cache = os.path.join(WORK, "wpc_latlon.npz")
        if os.path.exists(cache):
            z = np.load(cache)
            lat, lon = z["lat"], z["lon"]
        else:
            lat, lon = m.latlons()
            lat, lon = lat.astype("f4"), lon.astype("f4")
            os.makedirs(WORK, exist_ok=True)
            np.savez_compressed(cache, lat=lat, lon=lon)
        g.close()
        return v, lat, lon
    finally:
        os.unlink(p)


def scan(cfg, init=None):
    """Return dict(init=..., windows=[...]) describing each 24-h window ending at 00z/12z."""
    th = cfg["wpc"]["threshold_inches"]
    init = init or latest_init(th)
    if not init:
        return dict(init=None, windows=[])
    t0 = dt.datetime.strptime(init, "%Y%m%d%H")
    windows = []
    for fh in (24, 36, 48, 60, 72):
        url = f"{BASE}psnow24_ge{th}_{init}f{fh:03d}.grb"
        try:
            v, lat, lon = _read(url)
        except Exception as e:
            log("wpc: missing", url, e)
            continue
        sig = np.nan_to_num(v) >= cfg["wpc"]["prob_pct"]
        area = float(sig.sum()) * 2.54 * 2.54
        w = dict(start=iso(t0 + dt.timedelta(hours=fh - 24)), end=iso(t0 + dt.timedelta(hours=fh)), area_km2=round(area),
                 max_prob=round(float(np.nanmax(v)), 1))
        if area > 0:
            la, lo = lat[sig], lon[sig]
            w.update(bbox=[round(float(lo.min()), 2), round(float(la.min()), 2), round(float(lo.max()), 2), round(float(la.max()), 2)],
                     centroid=[round(float(lo.mean()), 2), round(float(la.mean()), 2)])
            # probability at verification cities (nearest 2.5 km cell)
            probs = {}
            for cid, name, st, cla, clo in CITIES:
                if not (w["bbox"][1] - 3 <= cla <= w["bbox"][3] + 3 and w["bbox"][0] - 3 <= clo <= w["bbox"][2] + 3):
                    continue
                d = (lat - cla) ** 2 + ((lon - clo) * np.cos(np.radians(cla))) ** 2
                j, i = np.unravel_index(np.argmin(d), d.shape)
                p = float(np.nan_to_num(v[j, i]))
                if p > 0:
                    probs[cid] = round(p)
            w["city_probs"] = probs
        w["significant"] = area >= cfg["wpc"]["min_area_km2"]
        windows.append(w)
    return dict(init=iso(t0), threshold_in=th, windows=windows)


def candidates(scan_result, cfg):
    """Group significant windows into storm candidates."""
    sig = [w for w in scan_result["windows"] if w.get("significant")]
    groups = []
    for w in sig:
        placed = False
        for g in groups:
            last = g[-1]
            if hav(last["centroid"][1], last["centroid"][0], w["centroid"][1], w["centroid"][0]) <= cfg["wpc"]["merge_km"] and \
               w["start"] <= last["end"]:
                g.append(w)
                placed = True
                break
        if not placed:
            groups.append([w])
    out = []
    for g in groups:
        peak = max(g, key=lambda w: w["area_km2"])
        bb = [min(w["bbox"][0] for w in g), min(w["bbox"][1] for w in g), max(w["bbox"][2] for w in g), max(w["bbox"][3] for w in g)]
        probs = {}
        for w in g:
            for k, p in w["city_probs"].items():
                probs[k] = max(probs.get(k, 0), p)
        out.append(dict(start=g[0]["start"], end=g[-1]["end"], peak=peak, bbox=bb, centroid=peak["centroid"],
                        region=region_name(peak["centroid"][1], peak["centroid"][0]), city_probs=probs,
                        max_area_km2=peak["area_km2"], max_prob=max(w["max_prob"] for w in g)))
    return out
