"""Weatherbots pipeline entry point.

  python run.py cycle                 # scheduled job: watch WPC, process new model cycles, write bouts, verify finished storms
  python run.py cycle --now 2026-02-20T09Z --no-wpc      # replay a past storm as if it were that time
  python run.py open --target 2026-02-23T12Z --bbox -78,38,-69,44 --start 2026-02-22T00Z --end 2026-02-24T00Z --region Northeast
"""
import argparse
import datetime as dt
import os
import sys

from wb.common import config, utcnow, iso, parse_iso, log
from wb import storm as S
from wb import wpc, cycle, discuss, verify, bout, casefile


def cycle_inits(state, now, cfg):
    tgt = parse_iso(state["target"])
    first = tgt - dt.timedelta(days=cfg["backfill_days"])
    first = first.replace(hour=0 if first.hour < 12 else 12)
    last = now - dt.timedelta(hours=6)
    out, t = [], first
    while t <= last and t < tgt - dt.timedelta(hours=12):
        out.append(t)
        t += dt.timedelta(hours=12)
    return out


def handle_storm(state, now, cfg, write_bouts=True):
    inits = cycle_inits(state, now, cfg)
    models = cfg["models"]
    for t in inits:
        key = iso(t)
        cyc = state["cycles"].get(key)
        recent = (now - t) < dt.timedelta(hours=48)
        if cyc and (len(cyc["runs"]) >= len(models) or not recent):
            continue
        log(f"{state['id']}: processing cycle {key}")
        cycle.process(state, t, models)
        S.save(state)
    # WPC discussion quotes up to now
    opened = parse_iso(state["target"]) - dt.timedelta(days=cfg["backfill_days"] + 1)
    # the model debate happens before the snow starts; later extended discussions are about the next system
    cutoff = min(now, parse_iso(state["window"]["start"]))
    q = discuss.quotes(state, opened, cutoff)
    q = [x for x in q if x["issued_iso"] <= cutoff.strftime("%Y-%m-%dT%H:%MZ")]
    if q:
        old = {x["text"] for x in state.get("quotes", [])}
        state["quotes"] = state.get("quotes", []) + [x for x in q if x["text"] not in old]
    # bout for the newest cycle with at least two models
    done = [i for i in sorted(state["cycles"]) if len(state["cycles"][i]["runs"]) >= 2]
    have = {b.get("init") for b in state.get("bouts", []) if b["id"] != "final"}
    if write_bouts and done and done[-1] not in have and state["status"] == "live":
        bout.write(state, done[-1], cfg)
    # verification once the storm is over
    end = parse_iso(state["window"]["end"])
    if state["status"] == "live" and now >= end + dt.timedelta(hours=cfg["close_after_hours"]):
        log(f"{state['id']}: verifying")
        verify.score(state)
        if write_bouts and done:
            bout.write(state, done[-1], cfg, final=True)
    casefile.build(state)
    S.save(state)


def cmd_cycle(a, cfg):
    now = parse_iso(a.now) if a.now else utcnow()
    if not a.no_wpc:
        try:
            sc = wpc.scan(cfg)
            log("WPC init", sc.get("init"), "windows:", [(w["start"], w["area_km2"]) for w in sc["windows"]])
            for c in wpc.candidates(sc, cfg):
                st = S.match_open(c, cfg)
                if st:
                    S.update_from_wpc(st, c, sc["init"])
                    log("WPC continues storm", st["id"])
                else:
                    tgt = iso(parse_iso(c["peak"]["start"]) + dt.timedelta(hours=12))
                    S.open_storm(tgt, c["bbox"], dict(start=c["start"], end=c["end"]), c["region"], c["city_probs"], cfg,
                                 source="wpc", wpc_init=sc["init"])
        except Exception as e:
            log("WPC scan failed:", repr(e))
    for st in S.all_states():
        if st["status"] == "live" and (not a.storm or st["id"] == a.storm):
            handle_storm(st, now, cfg, write_bouts=not a.no_bouts)
    S.index()


def cmd_open(a, cfg):
    bbox = [float(x) for x in a.bbox.split(",")]
    st = S.open_storm(a.target, bbox, dict(start=a.start, end=a.end), a.region, {}, cfg, source="manual", name=a.name)
    if a.stations:
        st["stations"] = a.stations.split(",")
        S.save(st)
    S.index()
    print(st["id"])


def cmd_bout(a, cfg):
    st = S.load(a.storm)
    if not st:
        raise SystemExit(f"no storm {a.storm}")
    init = a.init or [i for i in sorted(st["cycles"]) if len(st["cycles"][i]["runs"]) >= 2][-1]
    bout.write(st, init, cfg, final=a.final)
    casefile.build(st)
    S.save(st)
    S.index()


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cycle")
    c.add_argument("--now")
    c.add_argument("--no-wpc", action="store_true")
    c.add_argument("--no-bouts", action="store_true")
    c.add_argument("--storm")
    o = sub.add_parser("open")
    for k in ("target", "bbox", "start", "end", "region"):
        o.add_argument("--" + k, required=True)
    o.add_argument("--name")
    o.add_argument("--stations")
    b = sub.add_parser("bout")
    b.add_argument("--storm", required=True)
    b.add_argument("--init")
    b.add_argument("--final", action="store_true")
    a = p.parse_args()
    cfg = config()
    {"cycle": cmd_cycle, "open": cmd_open, "bout": cmd_bout}[a.cmd](a, cfg)


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main())
