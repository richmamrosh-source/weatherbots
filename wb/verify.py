"""After the storm: verifying analysis, Stage IV liquid, NWS climate-report snowfall, and per-run scores."""
import datetime as dt
import json
import math
import os
import tempfile

import numpy as np
import pygrib

from .common import http_get, iso, parse_iso, log, hav
from .cities import BY_ID
from .fields import record, _crop
from .track import track, sample, regrid
from .cycle import valid_times, grid_spec

BANDS = [("Day 5–7 (96–156 h)", 96, 999), ("Day 3–4 (60–84 h)", 60, 95), ("Final 48 h (24–48 h)", 0, 59)]


def analysis(state):
    tgt = parse_iso(state["target"])
    vts = valid_times(state)
    trs = {}
    for m in ("gfs", "ifs"):
        fb = {v: record(m, v, 0, "msl") for v in vts}
        trs[m] = track(fb, tgt, state["domain"])
    anl = []
    for v in vts:
        a, b = trs["gfs"].get(v), trs["ifs"].get(v)
        pts = [x for x in (a, b) if x]
        if pts:
            anl.append([round(float(np.mean([p[1] for p in pts])), 2), round(float(np.mean([p[0] for p in pts])), 2),
                        round(float(np.mean([p[2] for p in pts])), 1), iso(v)])
    g = grid_spec(state)
    zs = [record(m, tgt, 0, "z500") for m in ("gfs", "ifs")]
    zs = [z for z in zs if z is not None]
    zgrid = None
    if zs:
        grids = [regrid(z, g["lat0"], g["lon0"], g["d"], g["ny"], g["nx"]) for z in zs]
        zgrid = [None if any(v is None for v in col) else int(round(sum(col) / len(col))) for col in zip(*grids)]
    return anl, zgrid


def stage4(state):
    q0, q1 = parse_iso(state["window"]["start"]), parse_iso(state["window"]["end"])
    tot, meta = None, None
    t = q0 + dt.timedelta(hours=6)
    while t <= q1:
        url = f"https://mesonet.agron.iastate.edu/archive/data/{t:%Y/%m/%d}/stage4/ST4.{t:%Y%m%d%H}.06h.grib"
        try:
            blob = http_get(url)
            with tempfile.NamedTemporaryFile(suffix=".grb", delete=False) as f:
                f.write(blob)
                p = f.name
            g = pygrib.open(p)
            c = _crop(g.message(1), 1 / 25.4)
            g.close()
            os.unlink(p)
            v = np.where(np.nan_to_num(c["v"], nan=0.0) > 50, 0.0, np.nan_to_num(c["v"], nan=0.0))
            tot = v if tot is None else tot + v
            meta = c
        except Exception as e:
            log("stage4 missing", t, e)
        t += dt.timedelta(hours=6)
    if tot is None:
        return {}
    f = dict(kind="2d", lat=meta["lat"], lon=meta["lon"], v=tot)
    return {sid: round(sample(f, BY_ID[sid][3], BY_ID[sid][4]) or 0.0, 2) for sid in state["stations"]}


def _utc_offset(lon):
    return -5 if lon > -85.5 else -6 if lon > -102 else -7 if lon > -114.5 else -8


def cli_snow(state):
    q0, q1 = parse_iso(state["window"]["start"]), parse_iso(state["window"]["end"])
    out = {}
    cache = {}
    for sid in state["stations"]:
        c = BY_ID[sid]
        off = dt.timedelta(hours=_utc_offset(c[4]))
        a, b = q0 + off, q1 + off
        days = []
        d = a.date()
        while d <= b.date():
            day0 = dt.datetime.combine(d, dt.time())
            ov = (min(b, day0 + dt.timedelta(days=1)) - max(a, day0)).total_seconds() / 3600
            if ov >= 6:
                days.append(d.isoformat())
            d += dt.timedelta(days=1)
        yr = q0.year
        key = (sid, yr)
        if key not in cache:
            try:
                cache[key] = {r["valid"]: r for r in json.loads(http_get(f"https://mesonet.agron.iastate.edu/json/cli.py?station={sid}&year={yr}"))["results"]}
            except Exception as e:
                log("cli failed", sid, e)
                cache[key] = {}
        vals = [cache[key].get(d, {}).get("snow") for d in days]
        nums = [v for v in vals if isinstance(v, (int, float))]
        if nums:
            out[sid] = round(sum(nums), 1)
    return out


def score(state):
    anl, zgrid = analysis(state)
    tgt = state["target"]
    a_t = next((a for a in anl if a[3] == tgt), None)
    lq = stage4(state)
    sn = cli_snow(state)
    zmin_anl = None
    if zgrid:
        g = grid_spec(state)
        lon0, lat0, lon1, lat1 = state["domain"]
        core = [zgrid[j * g["nx"] + i] for j in range(g["ny"]) for i in range(g["nx"])
                if lat0 + 3 <= g["lat0"] + j * g["d"] <= lat1 - 2 and lon0 + 4 <= g["lon0"] + i * g["d"] <= lon1 - 4]
        core = [c for c in core if c is not None]
        zmin_anl = round(min(core) / 10, 1) if core else None
    for cyc in state["cycles"].values():
        for r in cyc["runs"].values():
            if a_t and r.get("at"):
                r["err_km"] = round(hav(r["at"][1], r["at"][0], a_t[1], a_t[0]))
                r["dp_mb"] = round(r["at"][2] - a_t[2], 1)
            if r.get("qpf") and lq:
                d = [r["qpf"][s] - lq[s] for s in r["qpf"] if s in lq]
                if d:
                    r["qpf_bias_in"] = round(float(np.mean(d)), 2)
                    r["qpf_mae_in"] = round(float(np.mean(np.abs(d))), 2)
            if zgrid and r.get("z500_grid"):
                e = [m - a for m, a in zip(r["z500_grid"], zgrid) if m is not None and a is not None]
                if e:
                    r["z500_rmse_m"] = round(float(np.sqrt(np.mean(np.square(e)))))
                if r.get("z500_min_dam") is not None and zmin_anl is not None:
                    r["z500_low_err_dam"] = round(r["z500_min_dam"] - zmin_anl, 1)
    sc = {}
    runs = [r for c in state["cycles"].values() for r in c["runs"].values()]
    for m in sorted({r["model"] for r in runs}):
        rows = {}
        for name, lo, hi in BANDS:
            rr = [r for r in runs if r["model"] == m and lo <= r["lead_h"] <= hi and "err_km" in r]
            if not rr:
                continue
            avg = lambda k: round(float(np.mean([r[k] for r in rr if k in r])), 2) if any(k in r for r in rr) else None
            rows[name] = dict(runs=len(rr), track_err_km=round(avg("err_km")), pressure_err_mb=round(avg("dp_mb"), 1),
                              qpf_bias_in=avg("qpf_bias_in"), qpf_mae_in=avg("qpf_mae_in"),
                              z500_closed_low_err_dam=(round(avg("z500_low_err_dam"), 1) if avg("z500_low_err_dam") is not None else None))
        sc[m] = rows
    state["verification"] = dict(analysis_track=anl, z500_anl_grid=zgrid, z500_anl_min_dam=zmin_anl,
                                 stage4_in=lq, snow_in=sn, scorecard=sc, verified=iso(dt.datetime.utcnow()))
    state["status"] = "verified"
    return state
