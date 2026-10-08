"""Process one model cycle (00z or 12z) for a storm: tracks, central pressure, QPF at the storm's stations,
500 mb heights at the target time."""
import concurrent.futures as cf
import datetime as dt

import numpy as np

from .common import iso, parse_iso, log, hav
from .cities import BY_ID
from .fields import record, available, MAX_STEP
from .track import track, sample, regrid

GRID_D = 0.5


def valid_times(state):
    t = parse_iso(state["target"])
    return [t + dt.timedelta(hours=h) for h in range(-36, 25, 6)]


def grid_spec(state):
    lon0, lat0, lon1, lat1 = state["domain"]
    lat0, lon0 = float(np.floor(lat0)), float(np.floor(lon0))
    ny = int((np.ceil(lat1) - lat0) / GRID_D) + 1
    nx = int((np.ceil(lon1) - lon0) / GRID_D) + 1
    return dict(lat0=lat0, lon0=lon0, d=GRID_D, ny=ny, nx=nx)


def needed(state, model, init):
    """Steps needed per field for this run."""
    tgt = parse_iso(state["target"])
    q0, q1 = parse_iso(state["window"]["start"]), parse_iso(state["window"]["end"])
    mx = MAX_STEP[model]
    h = lambda t: int((t - init).total_seconds() // 3600)
    out = {"msl": [h(v) for v in valid_times(state) if 0 <= h(v) <= mx]}
    out["z500"] = [h(tgt)] if 0 <= h(tgt) <= mx else []
    if model == "nam":
        out["tp12"] = [s for s in range(12, mx + 1, 12) if h(q0) < s <= h(q1)]
    else:
        out["tp"] = sorted({max(0, h(q0)), h(q1)}) if h(q1) <= mx and h(q1) > 0 else []
    return out


def ready(state, model, init):
    """True if the run is published far enough to cover the storm window."""
    n = needed(state, model, init)
    steps = [s for v in n.values() for s in v]
    if not steps:
        return False
    return available(model, init, max(steps))


def run_metrics(state, model, init):
    tgt = parse_iso(state["target"])
    n = needed(state, model, init)
    jobs = [(f, s) for f, ss in n.items() for s in ss]
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        res = dict(zip(jobs, ex.map(lambda j: record(model, init, j[1], j[0]), jobs)))
    fb = {init + dt.timedelta(hours=s): res.get(("msl", s)) for s in n["msl"]}
    if any(v is None for v in fb.values()) or (n["z500"] and res.get(("z500", n["z500"][0])) is None):
        log(f"{model} {iso(init)}: some fields failed to download; will retry next run")
        return None
    tr = track(fb, tgt, state["domain"])
    if not tr or tgt not in tr:
        return None
    at = tr.get(tgt)
    out = dict(model=model, init=iso(init), lead_h=int((tgt - init).total_seconds() // 3600),
               track=[[round(lo, 2), round(la, 2), round(p, 1), iso(t)] for t, (la, lo, p) in tr.items()])
    if at:
        out["at"] = [round(at[1], 2), round(at[0], 2), round(at[2], 1)]
    tmin = min(tr, key=lambda t: tr[t][2])
    out["minp"] = round(tr[tmin][2], 1)
    out["minp_time"] = iso(tmin)
    # QPF at stations over the storm window
    q = {}
    if model == "nam":
        bk = [res.get(("tp12", s)) for s in n.get("tp12", [])]
        if bk and all(b is not None for b in bk):
            for sid in state["stations"]:
                c = BY_ID[sid]
                vals = [sample(b, c[3], c[4]) for b in bk]
                q[sid] = round(sum(v for v in vals if v is not None), 2)
    else:
        tp = n.get("tp", [])
        if tp:
            a = res.get(("tp", tp[0])) if len(tp) > 1 else dict(kind="zero")
            b = res.get(("tp", tp[-1]))
            if b is not None and a is not None:
                for sid in state["stations"]:
                    c = BY_ID[sid]
                    vb, va = sample(b, c[3], c[4]), sample(a, c[3], c[4])
                    if vb is not None:
                        q[sid] = round(max(0.0, vb - (va or 0.0)), 2)
    if q:
        out["qpf"] = q
        q0 = parse_iso(state["window"]["start"])
        out["qpf_from"] = iso(max(q0, init))
    # 500 mb at target
    z = res.get(("z500", n["z500"][0])) if n["z500"] else None
    if z is not None:
        g = grid_spec(state)
        zz = regrid(z, g["lat0"], g["lon0"], g["d"], g["ny"], g["nx"])
        out["z500_grid"] = [None if v is None else int(round(v)) for v in zz]
        lon0, lat0, lon1, lat1 = state["domain"]
        core = [sample(z, la, lo) for la in np.arange(lat0 + 3, lat1 - 2, 0.5) for lo in np.arange(lon0 + 4, lon1 - 4, 0.5)]
        core = [c for c in core if c is not None]
        if core:
            out["z500_min_dam"] = round(min(core) / 10, 1)
    return out


def process(state, init, models):
    """Compute metrics for every model in this cycle that is published; store in state['cycles']."""
    key = iso(init)
    cyc = state["cycles"].setdefault(key, dict(runs={}))
    for m in models:
        if m in cyc["runs"]:
            continue
        if init >= parse_iso(state["target"]) - dt.timedelta(hours=12):
            continue
        n = needed(state, m, init)
        if not n["msl"] or not n["z500"]:
            continue  # target beyond this model's range (e.g. NAM before 84 h)
        try:
            if not ready(state, m, init):
                log(f"{m} {key}: not published yet")
                continue
            r = run_metrics(state, m, init)
        except Exception as e:
            log(f"{m} {key}: failed: {e!r}")
            continue
        if r:
            cyc["runs"][m] = r
            log(f"{m} {key}: low at target {r.get('at')} min {r.get('minp')}")
    # consensus position at target from the available runs
    pts = [r["at"] for r in cyc["runs"].values() if r.get("at")]
    if pts:
        cyc["consensus"] = [round(float(np.mean([p[0] for p in pts])), 2), round(float(np.mean([p[1] for p in pts])), 2),
                            round(float(np.mean([p[2] for p in pts])), 1)]
        for r in cyc["runs"].values():
            if r.get("at"):
                r["dcons_km"] = round(hav(r["at"][1], r["at"][0], cyc["consensus"][1], cyc["consensus"][0]))
    cyc["processed"] = iso(dt.datetime.utcnow())
    return cyc
