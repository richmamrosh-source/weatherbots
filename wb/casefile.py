"""Build the compact case.json the page reads (and the data block the bout writer sees)."""
import datetime as dt
import os

from .common import STORMS, write_json, parse_iso, hav, bearing_word
from .cities import BY_ID, CITIES
from .cycle import grid_spec

DAYN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def ddhh(s):
    return s[8:10] + s[11:13]


def label(s):
    t = parse_iso(s)
    return f"{t:%H}z {DAYN[t.weekday()]} {t:%b} {t.day}"


def near_place(lat, lon):
    """'95 km southeast of Atlantic City' — nearest verification city as a spoken reference."""
    c = min(CITIES, key=lambda c: hav(lat, lon, c[3], c[4]))
    d = hav(c[3], c[4], lat, lon)
    if d < 40:
        return f"over {c[1]}"
    return f"{round(d / 5) * 5:.0f} km {bearing_word(c[3], c[4], lat, lon)} of {c[1]}"


def build(state):
    ver = state.get("verification") or {}
    runs = []
    inits = sorted(state["cycles"])
    for i in inits:
        for m, r in sorted(state["cycles"][i]["runs"].items()):
            x = dict(m=m, i=i, lead=r["lead_h"], t=[[p[0], p[1], round(p[2]), ddhh(p[3])] for p in r["track"]],
                     minp=r.get("minp"))
            if r.get("at"):
                x["at"] = [r["at"][0], r["at"][1], round(r["at"][2], 1)]
            for k_src, k_dst in (("dcons_km", "dcons"), ("err_km", "err"), ("dp_mb", "dp"), ("qpf", "q"), ("qpf_bias_in", "qb"),
                                 ("qpf_mae_in", "qm"), ("z500_min_dam", "zmin"), ("z500_rmse_m", "zr"), ("z500_low_err_dam", "zerr")):
                if r.get(k_src) is not None:
                    x[k_dst] = r[k_src]
            runs.append(x)
    st = {}
    for sid in state["stations"]:
        c = BY_ID[sid]
        e = dict(n=c[1], lat=c[3], lon=c[4])
        if ver.get("snow_in", {}).get(sid) is not None:
            e["sn"] = ver["snow_in"][sid]
        if ver.get("stage4_in", {}).get(sid) is not None:
            e["lq"] = ver["stage4_in"][sid]
        st[sid] = e
    g = grid_spec(state)
    grids = dict(g, f={})
    for i in inits:
        for m, r in state["cycles"][i]["runs"].items():
            if r.get("z500_grid"):
                grids["f"][f"{m}|{i}"] = dict(z=r["z500_grid"])
    if ver.get("z500_anl_grid"):
        grids["f"]["anl"] = dict(z=ver["z500_anl_grid"])
    case = dict(
        id=state["id"], name=state["name"], status=state["status"], region=state["region"],
        domain=state["domain"], target=state["target"], target_label=label(state["target"]), window=state["window"],
        inits=inits, runs=runs,
        cons={i: state["cycles"][i]["consensus"] for i in inits if state["cycles"][i].get("consensus")},
        anl=[[a[0], a[1], round(a[2]), ddhh(a[3])] for a in ver.get("analysis_track", [])] or None,
        anl_zmin=ver.get("z500_anl_min_dam"),
        st=st, sc=ver.get("scorecard"),
        q=[dict(w=q["issued_est"], p=q["product"], t=q["text"]) for q in state.get("quotes", [])],
        grids=grids,
        lessons=state.get("lessons"),
    )
    write_json(os.path.join(STORMS, state["id"], "case.json"), case, compact=True)
    return case
