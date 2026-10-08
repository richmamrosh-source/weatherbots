"""Deterministic fallback bout, built only from the data. Used when the Claude API is unavailable."""
import random

from .cities import BY_ID
from .casefile import label

BOT = {"gfs": "gus", "ifs": "eccy", "aifs": "eccy", "nam": "nammy"}
NICK = {"gfs": "Gus", "ifs": "Eccy", "aifs": "the AIFS", "nam": "Nammy"}


def _pick(rng, xs):
    return xs[rng.randrange(len(xs))]


def bout(state, init, data, final=False):
    rng = random.Random(init + ("F" if final else ""))
    runs = data["runs"]
    cyc = data["this_cycle"]
    L = []

    def say(who, text, screen=None, cap=None, note=None, round_=None):
        l = dict(who=who, text=text)
        if screen:
            l["screen"] = screen
        if cap:
            l["cap"] = cap
        if note:
            l["note"] = note
        if round_:
            l["round"] = round_
        L.append(l)

    # Round 1: where is the low
    say("ref", f"Welcome back, weather geeks. Cycle {cyc['cycle']}. {cyc['hours_to_target']} hours until {data['storm']['target_time']}. "
               f"Gentlemen, where is the low?", f"rt:{init}", f"{cyc['cycle']} runs · low tracks", round_="Round 1 · Where is the low?")
    for m in ("gfs", "ifs", "aifs", "nam"):
        r = runs.get(m)
        who = BOT[m]
        if not r:
            if m == "nam":
                say("nammy", _pick(rng, ["I can't see that far yet. 84 hours. Save me a seat.", "Still out of my range! I'll be back."]),
                    f"range:{cyc['hours_to_target']}", "Forecast reach vs hours to the storm")
            continue
        if not r.get("low_at_target"):
            continue
        pre = "My little brother says" if m == "aifs" else _pick(rng, ["I've got it", "Right here", "Put it on the board"])
        say(who, f"{pre}: {r['pressure_at_target_mb']} mb, {r['low_at_target']}. Deepest {r['deepest_mb']} mb.",
            f"rt:{init}:{m}", f"{cyc['cycle']} · {m.upper()} highlighted",
            note=f"{m.upper()} {cyc['cycle']}: {r['pressure_at_target_mb']} mb at {data['storm']['target_time']}, {r.get('km_from_consensus', '?')} km from consensus.")
    far = max((m for m in runs if runs[m].get("km_from_consensus") is not None), key=lambda m: runs[m]["km_from_consensus"], default=None)
    if far and not final:
        say("ref", f"The judges note {NICK[far]} is the farthest from consensus: {runs[far]['km_from_consensus']} km.", f"err:{far}",
            "Distance from consensus by cycle")
    # Round 2: who moved
    movers = [(m, r["change_since_previous_run"]) for m, r in runs.items() if r.get("change_since_previous_run")]
    if movers:
        m, ch = max(movers, key=lambda x: x[1]["moved_km"])
        say("ref", "Round two. Who moved since last time?", f"trend:{m}", f"Every {m.upper()} run's low at target", round_="Round 2 · Who moved?")
        dirn = ch.get("moved_toward")
        if dirn:
            say(BOT[m], f"Fine. I moved {ch['moved_km']} km {dirn} since {ch['previous_run']}. Adjustments are a sign of intelligence.",
                note=f"{m.upper()} position change since {ch['previous_run']}: {ch['moved_km']} km.")
            jab = "eccy" if BOT[m] != "eccy" else "gus"
            say(jab, _pick(rng, [f"{ch['moved_km']} km. Some of us call that a wobble.", f"Moved {ch['moved_km']} km and calls it intelligence.",
                                 f"{ch['moved_km']} km in one cycle. Is the weathervane driving?"]))
        else:
            say(BOT[m], f"I barely moved. {ch['moved_km']} km. Rock solid.")
        for m2, ch2 in movers:
            if m2 != m and ch2.get("pressure_change_mb"):
                say(BOT[m2], f"And I'm {abs(ch2['pressure_change_mb'])} mb {'deeper' if ch2['pressure_change_mb'] < 0 else 'weaker'} than my last run.")
                break
    # Round 3: liquid
    spread = None
    for s in data["storm"]["stations"]:
        vals = {m: r["liquid_in"][s] for m, r in runs.items() if r.get("liquid_in", {}).get(s) is not None}
        if len(vals) >= 2:
            hi, lo = max(vals, key=vals.get), min(vals, key=vals.get)
            if spread is None or vals[hi] - vals[lo] > spread[3]:
                spread = (s, hi, lo, vals[hi] - vals[lo], vals)
    if spread:
        s, hi, lo, _, vals = spread
        sid = next(k for k in state["stations"] if BY_ID[k][1] == s)
        say("ref", f"Round three. The liquid. Biggest argument is over {s}.", f"qpfr:{hi}|{init}:{sid}", f"{hi.upper()} {cyc['cycle']} · liquid by station",
            round_="Round 3 · The liquid")
        say(BOT[hi], f"{vals[hi]} inches of liquid for {s}. Bring a shovel.")
        say(BOT[lo] if BOT[lo] != BOT[hi] else "ref", f"{vals[lo]} inches. Some of us don't panic.", f"qpfr:{lo}|{init}:{sid}", f"{lo.upper()} {cyc['cycle']} · liquid by station")
        if "nam" in runs and hi == "nam":
            say("eccy", "Cold air plus heavy precipitation. The child always does this.")
    # Round 4: 500 mb
    zs = [m for m in ("gfs", "ifs", "aifs", "nam") if runs.get(m, {}).get("z500_low_center_dam") is not None]
    if len(zs) >= 2:
        a, b = zs[0], zs[1]
        say("ref", "Round four. Upstairs. 500 millibars.", f"z5:{a}|{init},{b}|{init}", "500 mb at target", round_="Round 4 · Upstairs")
        za, zb = runs[a]["z500_low_center_dam"], runs[b]["z500_low_center_dam"]
        deeper = a if za < zb else b
        say(BOT[deeper], f"My closed low bottoms at {min(za, zb)} dam. Yours, {max(za, zb)}. Deeper trough, stronger storm.")
        other = b if deeper == a else a
        say(BOT[other], _pick(rng, ["Deeper is not the same as right.", "We'll see who closes it off first.", "Hectopascals. And patience."]))
    # Round 5: WPC
    if data.get("wpc_quotes"):
        q = data["wpc_quotes"][-1]
        say("ref", f"WPC weighs in: \"{q['text']}\"", f"quote:{q['n']}", f"{q['product']} · {q['issued']}", round_="Round 5 · What WPC said",
            note=f"Verbatim, {q['product']}, {q['issued']}.")
        say("gus", _pick(rng, ["I'll take that as a compliment.", "They noticed me. Good.", "Read it again, slower."]))
        say("eccy", _pick(rng, ["They are being polite to Gus.", "That is a statement about the guidance, Gus, not a fan letter."]))
    # Close
    if data.get("consensus"):
        say("ref", f"Standings after {cyc['cycle']}: consensus has {data['consensus']['pressure_mb']} mb, {data['consensus']['low_at_target']}. "
                   f"Next cycle in 12 hours. Check the ensembles.", f"rt:{init}", f"{cyc['cycle']} runs and consensus", round_="Standings")
    title = f"Cycle {cyc['cycle']}"
    verdict = dict(title="No decision yet", text=f"Consensus after {cyc['cycle']}: {data['consensus']['pressure_mb']} mb, {data['consensus']['low_at_target']}." if data.get("consensus") else "Waiting for more runs.")
    if final and data.get("verification"):
        v = data["verification"]
        sc = v["scorecard"]
        say("ref", "Final round. The verification.", "rverify", "Real low track and observed snowfall", round_="Verification")
        if v.get("real_low_at_target"):
            say("ref", f"The real low: {v['real_low_at_target']['pressure_mb']} mb, {v['real_low_at_target']['position']}.")
        best = {}
        for band in ("Day 5–7 (96–156 h)", "Day 3–4 (60–84 h)", "Final 48 h (24–48 h)"):
            rows = {m: sc[m][band] for m in sc if band in sc[m]}
            if rows:
                best[band] = min(rows, key=lambda m: rows[m]["track_err_km"])
        for k, (band, m) in enumerate(best.items()):
            say(BOT[m], f"{band}: best track. {sc[m][band]['track_err_km']} km average miss.", f"band:{k}", f"Scorecard · {band}")
        say("ref", "Judges' decision is on the board.", "matrix", "Every run, scored")
        winners = sorted(set(best.values()))
        title = "Final: verification"
        verdict = dict(title="Decision", text="Best by window: " + "; ".join(f"{b}: {m.upper()}" for b, m in best.items()) + ".")
    return dict(title=title, verdict=verdict, lines=L)
