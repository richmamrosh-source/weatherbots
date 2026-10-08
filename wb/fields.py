"""Byte-range GRIB2 retrieval for GFS, NAM, ECMWF IFS and ECMWF AIFS from public archives.

Fields: msl (hPa), z500 (m), tp (inches accumulated from init; GFS/IFS/AIFS) and tp12 (NAM 12-h bucket, inches).
Every record is cropped to North America and cached under work/fields/.
"""
import json
import os
import tempfile
import urllib.error
import datetime as dt

import numpy as np
import pygrib

from .common import WORK, http_get, http_exists, ymdh

BOX = dict(lat0=18.0, lat1=58.0, lon0=-135.0, lon1=-45.0)
MAX_STEP = {"gfs": 384, "ifs": 240, "aifs": 360, "nam": 84}


def _crop(msg, scale=1.0):
    vals = msg.values * scale
    lats, lons = msg.latlons()
    lons = np.where(lons > 180, lons - 360, lons)
    if np.allclose(lats[:, 0], lats[:, -1]) and np.allclose(lons[0, :], lons[-1, :]):
        la, lo = lats[:, 0], lons[0, :]
        iy = np.where((la >= BOX["lat0"]) & (la <= BOX["lat1"]))[0]
        ix = np.where((lo >= BOX["lon0"]) & (lo <= BOX["lon1"]))[0]
        sub = vals[np.ix_(iy, ix)]
        la, lo = la[iy], lo[ix]
        if la[0] > la[-1]:
            sub, la = sub[::-1], la[::-1]
        return dict(kind="reg", lat=la.astype("f4"), lon=lo.astype("f4"), v=np.asarray(sub, dtype="f4"))
    m = (lats >= BOX["lat0"]) & (lats <= BOX["lat1"]) & (lons >= BOX["lon0"]) & (lons <= BOX["lon1"])
    jj, ii = np.where(m)
    j0, j1, i0, i1 = jj.min(), jj.max() + 1, ii.min(), ii.max() + 1
    return dict(kind="2d", lat=lats[j0:j1, i0:i1].astype("f4"), lon=lons[j0:j1, i0:i1].astype("f4"),
                v=np.asarray(np.ma.filled(vals[j0:j1, i0:i1], np.nan), dtype="f4"))


def decode(blob, scale=1.0):
    with tempfile.NamedTemporaryFile(suffix=".grib2", delete=False) as f:
        f.write(blob)
        p = f.name
    try:
        g = pygrib.open(p)
        out = _crop(g.message(1), scale)
        g.close()
        return out
    finally:
        os.unlink(p)


def _ncep_range(idx_url, pred):
    lines = http_get(idx_url).decode().strip().split("\n")
    for i, ln in enumerate(lines):
        if pred(ln):
            start = int(ln.split(":")[1])
            end = int(lines[i + 1].split(":")[1]) - 1 if i + 1 < len(lines) else ""
            return (start, end)
    return None


def _ec_range(idx_url, pred):
    for ln in http_get(idx_url).decode().strip().split("\n"):
        j = json.loads(ln)
        if pred(j):
            return (j["_offset"], j["_offset"] + j["_length"] - 1)
    return None


def urls(model, init, step):
    i = ymdh(init)
    if model == "gfs":
        b = f"https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.{i[:8]}/{i[8:]}/atmos/gfs.t{i[8:]}z.pgrb2.0p25.f{step:03d}"
        return b, b + ".idx"
    if model == "nam":
        b = f"https://noaa-nam-pds.s3.amazonaws.com/nam.{i[:8]}/nam.t{i[8:]}z.awphys{step:02d}.tm00.grib2"
        return b, b + ".idx"
    stream = "scda" if (model == "ifs" and i[8:] in ("06", "18")) else "oper"
    sub = f"ifs/0p25/{stream}" if model == "ifs" else "aifs-single/0p25/oper"
    b = f"https://ecmwf-forecasts.s3.amazonaws.com/{i[:8]}/{i[8:]}z/{sub}/{i[:8]}{i[8:]}0000-{step}h-{stream}-fc"
    return b + ".grib2", b + ".index"


def available(model, init, step):
    return http_exists(urls(model, init, step)[1])


def record(model, init, step, field):
    """Return a cropped field dict, or None if it does not exist. Cached on disk."""
    i = ymdh(init)
    cache = os.path.join(WORK, "fields", model, f"{i}_{field}_{step:03d}.npz")
    if os.path.exists(cache):
        z = np.load(cache)
        if str(z["kind"]) == "none":
            return None
        return {k: (str(z[k]) if k == "kind" else z[k]) for k in z.files}
    if field in ("tp",) and step == 0:
        return dict(kind="zero")
    data_url, idx_url = urls(model, init, step)
    try:
        if model in ("gfs", "nam"):
            if field == "msl":
                pred = (lambda l: ":PRMSL:mean sea level:" in l) if model == "gfs" else (lambda l: ":MSLET:mean sea level:" in l)
            elif field == "z500":
                pred = lambda l: ":HGT:500 mb:" in l
            elif field == "tp":
                pred = lambda l: ":APCP:surface:" in l and (f":0-{step} hour acc" in l or (step % 24 == 0 and f":0-{step // 24} day acc" in l))
            elif field == "tp12":
                pred = lambda l: f":APCP:surface:{step - 12}-{step} hour acc" in l
            rng = _ncep_range(idx_url, pred)
        else:
            zname = "gh" if model == "ifs" else "z"
            pred = {"msl": lambda j: j.get("param") == "msl",
                    "z500": lambda j: j.get("param") == zname and j.get("levelist") == "500",
                    "tp": lambda j: j.get("param") == "tp"}[field]
            rng = _ec_range(idx_url, pred)
    except urllib.error.HTTPError as e:
        rng = None if e.code in (403, 404) else "retry"
    except Exception:
        rng = "retry"
    if rng == "retry":
        return None
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    if rng is None:
        np.savez_compressed(cache, kind="none")
        return None
    if field == "msl":
        scale = 0.01
    elif field in ("tp", "tp12"):
        scale = (1000.0 / 25.4) if model == "ifs" else (1.0 / 25.4)
    elif field == "z500" and model == "aifs":
        scale = 1 / 9.80665
    else:
        scale = 1.0
    try:
        out = decode(http_get(data_url, rng), scale)
    except Exception as e:  # transient failure: don't cache, let the next run retry
        from .common import log
        log(f"record {model} {i} {field} f{step}: {e!r}")
        return None
    np.savez_compressed(cache, **out)
    return out
