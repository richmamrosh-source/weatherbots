"""Surface-low tracking and field sampling."""
import math

import numpy as np

from .common import hav


def latlon2d(f):
    if f["kind"] == "reg":
        lon2, lat2 = np.meshgrid(f["lon"], f["lat"])
        return lat2, lon2
    return f["lat"], f["lon"]


def minima(f, win_km=220.0, cap=1016.0, box=None):
    """Local minima of a pressure field as (lat, lon, p), refined to sub-grid with a parabolic fit."""
    v = np.nan_to_num(f["v"], nan=1100.0)
    lat2, lon2 = latlon2d(f)
    if f["kind"] == "reg":
        dlat = abs(float(f["lat"][1] - f["lat"][0]))
        n = max(2, int(round(win_km / 111.0 / dlat)))
    else:
        n = max(2, int(round(win_km / 12.0)))
    H, W = v.shape
    pad = np.pad(v, n, mode="edge")
    m = np.full_like(v, np.inf)
    for dj in range(-n, n + 1):
        for di in range(-n, n + 1):
            m = np.minimum(m, pad[n + dj:n + dj + H, n + di:n + di + W])
    jj, ii = np.where((v <= m) & (v < cap))
    out = []
    for j, i in zip(jj, ii):
        if not (1 <= j < H - 1 and 1 <= i < W - 1):
            continue
        dy = 0.5 * (v[j - 1, i] - v[j + 1, i]) / (v[j - 1, i] - 2 * v[j, i] + v[j + 1, i] + 1e-9)
        dx = 0.5 * (v[j, i - 1] - v[j, i + 1]) / (v[j, i - 1] - 2 * v[j, i] + v[j, i + 1] + 1e-9)
        dy, dx = max(-.5, min(.5, dy)), max(-.5, min(.5, dx))
        la = float(lat2[j, i] + dy * (lat2[j + 1, i] - lat2[j - 1, i]) / 2)
        lo = float(lon2[j, i] + dx * (lon2[j, i + 1] - lon2[j, i - 1]) / 2)
        if box and not (box[1] <= la <= box[3] and box[0] <= lo <= box[2]):
            continue
        out.append((la, lo, float(v[j, i])))
    return out


def track(fields_by_time, anchor_time, anchor_box, step_km=750):
    """Anchor on the deepest low inside anchor_box (lon0, lat0, lon1, lat1) at anchor_time, then follow
    the nearest minimum backward and forward through the other times."""
    times = sorted(t for t, f in fields_by_time.items() if f is not None)
    if not times:
        return {}
    mins = {t: minima(fields_by_time[t]) for t in times}
    at = anchor_time if anchor_time in mins else min(times, key=lambda t: abs((t - anchor_time).total_seconds()))
    lo0, la0, lo1, la1 = anchor_box
    cand = [m for m in mins[at] if la0 <= m[0] <= la1 and lo0 <= m[1] <= lo1]
    if not cand:
        return {}
    start = min(cand, key=lambda m: m[2])
    tr = {at: start}

    def follow(seq):
        prev = start
        for t in seq:
            c = [m for m in mins[t] if hav(prev[0], prev[1], m[0], m[1]) <= step_km]
            if not c:
                break
            nxt = min(c, key=lambda m: hav(prev[0], prev[1], m[0], m[1]) + 15 * max(0.0, m[2] - prev[2]))
            tr[t] = nxt
            prev = nxt

    follow([t for t in reversed(times) if t < at])
    follow([t for t in times if t > at])
    return dict(sorted(tr.items()))


def sample(f, lat, lon):
    """Bilinear for regular grids, nearest neighbour for projected grids. NaN-safe."""
    if f is None:
        return None
    if f["kind"] == "zero":
        return 0.0
    if f["kind"] == "reg":
        la, lo, v = f["lat"], f["lon"], f["v"]
        j = int(np.clip(np.searchsorted(la, lat) - 1, 0, len(la) - 2))
        i = int(np.clip(np.searchsorted(lo, lon) - 1, 0, len(lo) - 2))
        ty = (lat - la[j]) / (la[j + 1] - la[j])
        tx = (lon - lo[i]) / (lo[i + 1] - lo[i])
        val = (1 - ty) * ((1 - tx) * v[j, i] + tx * v[j, i + 1]) + ty * ((1 - tx) * v[j + 1, i] + tx * v[j + 1, i + 1])
        return None if not np.isfinite(val) else float(val)
    d = (f["lat"] - lat) ** 2 + ((f["lon"] - lon) * math.cos(math.radians(lat))) ** 2
    j, i = np.unravel_index(np.argmin(d), d.shape)
    val = f["v"][j, i]
    return None if not np.isfinite(val) else float(val)


def regrid(f, lat0, lon0, d, ny, nx):
    """Sample a field onto a regular lat/lon grid (row-major, south to north)."""
    out = []
    for j in range(ny):
        la = lat0 + j * d
        for i in range(nx):
            v = sample(f, la, lon0 + i * d)
            out.append(None if v is None else v)
    return out
