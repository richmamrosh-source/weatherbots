"""Storm records: open from a WPC candidate (or manually), merge, persist. One folder per storm under site/data/storms/."""
import datetime as dt
import os
import re

from .common import STORMS, DATA, read_json, write_json, iso, parse_iso, hav, log
from .cities import CITIES, BY_ID
from .fields import BOX


def storm_dir(sid):
    return os.path.join(STORMS, sid)


def load(sid):
    return read_json(os.path.join(storm_dir(sid), "state.json"))


def save(state):
    write_json(os.path.join(storm_dir(state["id"]), "state.json"), state)


def all_states():
    out = []
    if not os.path.isdir(STORMS):
        return out
    for sid in sorted(os.listdir(STORMS)):
        s = load(sid)
        if s:
            out.append(s)
    return out


def _domain(bbox):
    lon0, lat0, lon1, lat1 = bbox
    d = [lon0 - 10, lat0 - 8, lon1 + 8, lat1 + 4]
    d = [max(d[0], BOX["lon0"] + 1), max(d[1], BOX["lat0"] + 1), min(d[2], BOX["lon1"] - 1), min(d[3], BOX["lat1"] - 1)]
    return [round(x, 1) for x in d]


def _pick_stations(bbox, city_probs, n):
    ranked = sorted(city_probs.items(), key=lambda kv: -kv[1])
    ids = [k for k, p in ranked if p >= 10][:n]
    if len(ids) < n:
        cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
        near = sorted(CITIES, key=lambda c: hav(cy, cx, c[3], c[4]))
        for c in near:
            if c[0] not in ids:
                ids.append(c[0])
            if len(ids) >= n:
                break
    return ids


def make_id(target, region):
    return f"{target[:10]}-{re.sub(r'[^a-z]+', '-', region.lower()).strip('-')}"


def open_storm(target, bbox, window, region, city_probs, cfg, source, wpc_init=None, name=None):
    sid = make_id(target, region)
    t = parse_iso(target)
    state = dict(
        id=sid,
        name=name or f"{region} snowstorm, {t:%b} {t.day}, {t.year}",
        region=region,
        opened=iso(dt.datetime.utcnow()),
        source=source,
        status="live",
        target=target,
        window=window,
        bbox=bbox,
        domain=_domain(bbox),
        stations=_pick_stations(bbox, city_probs, cfg["stations_per_storm"]),
        wpc=dict(first_init=wpc_init, latest_init=wpc_init, history=[]),
        cycles={},
        bouts=[],
        quotes=[],
        verification=None,
    )
    save(state)
    log("opened storm", sid, state["name"], "target", target, "domain", state["domain"])
    return state


def match_open(cand, cfg):
    """An open storm this WPC candidate belongs to, if any."""
    for s in all_states():
        if s["status"] != "live":
            continue
        t = parse_iso(s["target"])
        ct = parse_iso(cand["peak"]["start"]) + dt.timedelta(hours=12)
        cx, cy = cand["centroid"]
        sx, sy = (s["bbox"][0] + s["bbox"][2]) / 2, (s["bbox"][1] + s["bbox"][3]) / 2
        if abs((ct - t).total_seconds()) <= cfg["wpc"]["merge_hours"] * 3600 and hav(cy, cx, sy, sx) <= cfg["wpc"]["merge_km"]:
            return s
    return None


def update_from_wpc(state, cand, wpc_init):
    """Extend the snow window and record WPC history. Target and domain stay fixed once a storm opens
    so that every cycle is scored the same way."""
    w = state["window"]
    w["start"] = min(w["start"], cand["start"])
    w["end"] = max(w["end"], cand["end"])
    state["wpc"]["latest_init"] = wpc_init
    state["wpc"]["history"].append(dict(init=wpc_init, max_area_km2=cand["max_area_km2"], max_prob=cand["max_prob"],
                                        peak=[cand["peak"]["start"], cand["peak"]["end"]]))
    state["wpc"]["history"] = state["wpc"]["history"][-20:]
    save(state)


def index():
    """Write site/data/index.json listing storms and their bouts for the page."""
    items = []
    for s in all_states():
        items.append(dict(id=s["id"], name=s["name"], status=s["status"], target=s["target"], region=s["region"],
                          bouts=[dict(id=b["id"], title=b["title"], init=b.get("init"), mode=b.get("mode")) for b in s.get("bouts", [])]))
    items.sort(key=lambda x: x["target"], reverse=True)
    path = os.path.join(DATA, "index.json")
    old = read_json(path, {})
    if old.get("storms") == items:
        return  # unchanged: don't touch the file, so quiet runs make no commit
    write_json(path, dict(updated=iso(dt.datetime.utcnow()), storms=items))
