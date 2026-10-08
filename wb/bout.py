"""Write a Weatherbots bout for a storm cycle (or the final verification bout).

Claude writes the script through a forced tool call; every number in the script must appear in the data the
bots were given. If the API key is missing, the call fails, or the check fails twice, a template bout is written.
"""
import datetime as dt
import json
import os
import re
import urllib.request

from .common import STORMS, read_json, write_json, iso, parse_iso, log, hav, bearing_word
from .cities import BY_ID
from .casefile import label, near_place
from . import template

NAMES = {"gfs": "GFS (Big Gus)", "ifs": "ECMWF IFS (Eccy)", "aifs": "ECMWF AIFS (Eccy's little brother)", "nam": "NAM (Little Nammy)"}

SYSTEM = """You write scripts for "Weatherbots", a web show where three cartoon robots argue about which weather model is right about an approaching storm. Weather geeks watch it; the humor is affectionate and technically literate. Lines are read aloud by text-to-speech and shown in speech bubbles, while a jumbotron behind the bots shows the map or chart you choose for each line.

THE CAST
- The Blend ("ref"): the referee, voiced as the National Blend of Models. Calm, dry, fair. Opens each round, reads WPC quotes, keeps score.
- Big Gus ("gus"): the GFS, NOAA's global model, runs four times a day. Brash, loud, American, loves consistency streaks and run counts. Real habits it must own when the data shows them: tracks drifting northwest in later runs, flip-flopping run to run, convective spin-up, a GEFS ensemble that is underdispersive (the members hug the control). Weathervane on his head never stops spinning.
- Eccy the Euro ("eccy"): the ECMWF IFS from Reading, England. Polished, dry British wit, says "hectopascals" and "twelve zed", points to his season-long verification record. Real habits: too dry in heavy-precipitation events, too wet with light drizzle, summer warm bias, usually the most consistent. His AI little brother, the AIFS, is not on stage; Eccy speaks for him, sometimes proudly, sometimes through gritted teeth.
- Little Nammy ("nammy"): the NAM, 12 km with a 3 km nest, only sees 84 hours ahead and shows up late shouting. Real habits: over-forecasts precipitation and snow in cold air, cool daytime surface bias, keeps surface moisture instead of mixing it out, initialized from NCEP's system, code frozen since 2017. Excitable and earnest.

HOW A BOUT WORKS
- Every argument is about the DATA provided: where each model puts the surface low at the target time, how deep it is, how far it sits from the consensus of the other models, how much liquid it gives each city, how it changed since its previous run, the 500 mb heights, and what WPC wrote.
- The bots remember what they said last time (LAST_BOUT). Call back to it: gloat when a model held its position, needle a model that moved, make a bot eat its own words when the data turned against it.
- Before verification nobody knows who is right. The ref keeps it open and says what to watch next. In the FINAL bout (verification present) the ref gives a decision based on the scorecard.

HARD RULES
1. Use ONLY numbers that appear in DATA, written as digits ("967 mb", "1.65 inches", "144 hours"). Never invent a number, and never spell numbers out as words above twelve.
2. Quote WPC only verbatim from DATA.wpc_quotes, and only with the screen "quote:<n>" for that quote's n. Skip any quote that is clearly about a different weather system. Never invent quotes from anyone.
3. If a model is missing from a cycle, say it sat this one out; do not make up its numbers.
4. Keep every line under 45 words. Keep it PG, warm, funny, and accurate. No real people.
5. Use the screen catalog in DATA.screens. Pick the screen that shows what the line is about; set "cap" to a short caption for it (under 70 characters). A line may omit the screen to keep the previous one.
6. Add a short factual "note" (one sentence citing the data) to any line that makes a factual claim.
7. Organize into 4-6 rounds; mark the first line of each round with "round" (for example "Round 2 · The 500 mb argument").
"""

TOOL = {
    "name": "submit_bout",
    "description": "Submit the finished Weatherbots bout script.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short bout title, e.g. 'Cycle 12z Thu Feb 19: The wobble'"},
            "verdict": {"type": "object", "properties": {"title": {"type": "string"}, "text": {"type": "string"}},
                        "required": ["title", "text"]},
            "lines": {"type": "array", "items": {"type": "object", "properties": {
                "round": {"type": "string"},
                "who": {"type": "string", "enum": ["ref", "gus", "eccy", "nammy"]},
                "text": {"type": "string"},
                "note": {"type": "string"},
                "screen": {"type": "string"},
                "cap": {"type": "string"}}, "required": ["who", "text"]}},
        },
        "required": ["title", "verdict", "lines"],
    },
}


# ---------------------------------------------------------------- data for the writer
def _prev_run(state, model, init):
    prior = [i for i in sorted(state["cycles"]) if i < init and model in state["cycles"][i]["runs"]]
    return (prior[-1], state["cycles"][prior[-1]]["runs"][model]) if prior else (None, None)


def _qnames(q, stations):
    return {BY_ID[s][1]: v for s, v in q.items() if s in stations}


def build_data(state, init, final=False):
    cyc = state["cycles"][init]
    tgt = state["target"]
    runs = {}
    for m, r in sorted(cyc["runs"].items()):
        x = dict(model=NAMES[m], lead_hours=r["lead_h"], deepest_mb=round(r["minp"]), deepest_time=label(r["minp_time"]))
        if r.get("at"):
            x.update(low_at_target=near_place(r["at"][1], r["at"][0]), pressure_at_target_mb=round(r["at"][2]))
        if r.get("dcons_km") is not None:
            x["km_from_consensus"] = r["dcons_km"]
        if r.get("qpf"):
            x["liquid_in"] = _qnames(r["qpf"], state["stations"])
            x["liquid_counts_from"] = label(r["qpf_from"])
        if r.get("z500_min_dam") is not None:
            x["z500_low_center_dam"] = r["z500_min_dam"]
        pi, pr = _prev_run(state, m, init)
        if pr and pr.get("at") and r.get("at"):
            d = hav(pr["at"][1], pr["at"][0], r["at"][1], r["at"][0])
            ch = dict(previous_run=label(pi), moved_km=round(d), pressure_change_mb=round(r["at"][2] - pr["at"][2]))
            if d >= 25:
                ch["moved_toward"] = bearing_word(pr["at"][1], pr["at"][0], r["at"][1], r["at"][0])
            if r.get("qpf") and pr.get("qpf"):
                ch["liquid_change_in"] = {BY_ID[s][1]: round(r["qpf"][s] - pr["qpf"][s], 2) for s in r["qpf"] if s in pr["qpf"]}
            x["change_since_previous_run"] = ch
        if final and r.get("err_km") is not None:
            x["verified"] = dict(km_from_real_low=r["err_km"], pressure_error_mb=r.get("dp_mb"),
                                 liquid_bias_in=r.get("qpf_bias_in"), liquid_mean_abs_error_in=r.get("qpf_mae_in"),
                                 z500_low_error_dam=r.get("z500_low_err_dam"), z500_rms_error_m=r.get("z500_rmse_m"))
        runs[m] = x
    hist = []
    for i in sorted(state["cycles"]):
        for m, r in sorted(state["cycles"][i]["runs"].items()):
            h = dict(cycle=label(i), model=m, lead_hours=r["lead_h"])
            if r.get("at"):
                h.update(low_at_target=near_place(r["at"][1], r["at"][0]), pressure_mb=round(r["at"][2]))
            if r.get("dcons_km") is not None:
                h["km_from_consensus"] = r["dcons_km"]
            if r.get("qpf"):
                h["mean_liquid_in"] = round(sum(r["qpf"].values()) / len(r["qpf"]), 2)
            if final and r.get("err_km") is not None:
                h["km_from_real_low"] = r["err_km"]
                h["pressure_error_mb"] = r.get("dp_mb")
            hist.append(h)
    cons = cyc.get("consensus")
    last = [b for b in state.get("bouts", []) if b.get("init") != init or final]
    last_lines = None
    if last:
        lb = read_json(os.path.join(STORMS, state["id"], "bouts", last[-1]["id"] + ".json"))
        if lb:
            last_lines = dict(title=lb["title"], lines=[dict(who=l["who"], text=l["text"]) for l in lb["lines"]])
    seen_q = set(state.get("quotes_used", []))
    quotes = [dict(n=n, issued=q["issued_est"], product=q["product"], text=q["text"]) for n, q in enumerate(state.get("quotes", []))]
    fresh = [q for q in quotes if q["n"] not in seen_q][-8:] or quotes[-4:]
    data = dict(
        storm=dict(name=state["name"], region=state["region"], target_time=label(tgt),
                   snow_window=[label(state["window"]["start"]), label(state["window"]["end"])],
                   stations=[BY_ID[s][1] for s in state["stations"]],
                   wpc_latest=state["wpc"]["history"][-1] if state["wpc"].get("history") else None),
        this_cycle=dict(cycle=label(init), hours_to_target=int((parse_iso(tgt) - parse_iso(init)).total_seconds() // 3600),
                        models_present=sorted(cyc["runs"]), models_missing=sorted(set(["gfs", "ifs", "aifs", "nam"]) - set(cyc["runs"]))),
        runs=runs,
        consensus=dict(low_at_target=near_place(cons[1], cons[0]), pressure_mb=round(cons[2])) if cons else None,
        history=hist[-48:],
        wpc_quotes=fresh,
        last_bout=last_lines,
    )
    if final and state.get("verification"):
        v = state["verification"]
        a = next((x for x in v["analysis_track"] if x[3] == tgt), None)
        data["verification"] = dict(
            real_low_at_target=(dict(position=near_place(a[1], a[0]), pressure_mb=round(a[2])) if a else None),
            real_deepest_mb=round(min(x[2] for x in v["analysis_track"])) if v["analysis_track"] else None,
            observed={BY_ID[s][1]: dict(snow_in=v["snow_in"].get(s), liquid_in=v["stage4_in"].get(s)) for s in state["stations"]},
            scorecard=v["scorecard"], z500_real_low_center_dam=v.get("z500_anl_min_dam"))
    data["screens"] = screens(state, init, final)
    return data


def screens(state, init, final):
    cyc = state["cycles"][init]
    ms = sorted(cyc["runs"])
    inits = sorted(state["cycles"])
    out = [dict(spec="card:gus", shows="Big Gus profile card"), dict(spec="card:eccy", shows="Eccy profile card"),
           dict(spec="card:nammy", shows="Little Nammy profile card")]
    for i in inits[-6:] + ([inits[0]] if len(inits) > 6 else []):
        out.append(dict(spec=f"rt:{i}", shows=f"map: every model's low track from the {label(i)} cycle" + (" vs the real low" if final else " and the consensus")))
        for m in sorted(state["cycles"][i]["runs"]):
            out.append(dict(spec=f"rt:{i}:{m}", shows=f"same map, highlighting {m}"))
    for m in ms:
        out.append(dict(spec=f"trend:{m}", shows=f"map: where each {m} run has put the low at the target time, cycle by cycle"))
        out.append(dict(spec=f"err:{m}", shows=f"chart: {'miss vs the real low' if final else 'distance from consensus'} by cycle, highlighting {m}"))
    out.append(dict(spec="minp", shows="chart: deepest pressure of each model by cycle"))
    for m in ms:
        if cyc["runs"][m].get("qpf"):
            for s in state["stations"][:6]:
                out.append(dict(spec=f"qpfr:{m}|{init}:{s}", shows=f"bars: {m} {label(init)} liquid at every station, highlighting {BY_ID[s][1]}" + (" (observed ticks)" if final else "")))
    zs = [m for m in ms if cyc["runs"][m].get("z500_grid")]
    for a in range(len(zs)):
        for b in range(a + 1, len(zs)):
            out.append(dict(spec=f"z5:{zs[a]}|{init},{zs[b]}|{init}", shows=f"500 mb heights at target: {zs[a]} vs {zs[b]}" + (" vs the analysis" if final else "")))
    for n, q in enumerate(state.get("quotes", [])):
        out.append(dict(spec=f"quote:{n}", shows=f"WPC quote #{n}"))
    out.append(dict(spec=f"range:{int((parse_iso(state['target']) - parse_iso(init)).total_seconds() // 3600)}", shows="each model's forecast reach vs hours to the storm"))
    out.append(dict(spec="lineage", shows="diagram: the NAM starts from NCEP's analysis system"))
    if final:
        out += [dict(spec="matrix", shows="grid: every run colored by miss distance"), dict(spec="band:0", shows="scorecard days 5-7"),
                dict(spec="band:1", shows="scorecard days 3-4"), dict(spec="band:2", shows="scorecard final 48 h"),
                dict(spec="rverify", shows="map: real low track and observed snowfall"), dict(spec="lesson", shows="closing lessons board")]
    return out


# ---------------------------------------------------------------- number checking
NUM = re.compile(r"(?<![A-Za-z])(\d+(?:\.\d+)?)")
WORDS = re.compile(r"\b(thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand)\b", re.I)


def allowed_numbers(data):
    d = dict(data)
    d.pop("screens", None)  # screen ids contain dates and station codes, not spoken numbers
    blob = json.dumps(d)
    vals = set()
    for s in NUM.findall(blob):
        x = float(s)
        vals |= {round(x, 2), round(x, 1), float(round(x)), round(abs(x), 2), float(round(abs(x)))}
    vals |= {float(n) for n in range(0, 25)} | {float(y) for y in range(2017, 2031)}
    return vals


def check(bout, data):
    allowed = allowed_numbers(data)
    specs = {s["spec"] for s in data["screens"]}
    problems = []
    lines = bout.get("lines", [])
    if not (12 <= len(lines) <= 60):
        problems.append(f"{len(lines)} lines; write between 24 and 34")
    for who in ("gus", "eccy", "nammy", "ref"):
        if sum(1 for l in lines if l.get("who") == who) < 2:
            problems.append(f"{who} speaks fewer than 2 times")
    for k, l in enumerate(lines):
        for fld in ("text", "note", "cap"):
            t = l.get(fld) or ""
            t2 = re.sub(r"\b\d{1,2}z\b|\b\d{1,2} ?zed\b", "", t)  # cycle names are fine
            for s in NUM.findall(t2):
                x = float(s)
                if round(x, 2) not in allowed and round(x, 1) not in allowed and float(round(x)) not in allowed:
                    problems.append(f"line {k + 1} {fld}: number {s} is not in DATA")
            if WORDS.search(t):
                problems.append(f"line {k + 1} {fld}: spelled-out number '{WORDS.search(t).group(0)}'; use digits")
        if l.get("screen") and l["screen"] not in specs:
            problems.append(f"line {k + 1}: screen '{l['screen']}' is not in the catalog")
        if l.get("screen", "").startswith("quote:"):
            n = int(l["screen"].split(":")[1])
            q = next((q for q in data["wpc_quotes"] if q["n"] == n), None)
            if q is None:
                pass  # older quote shown on screen, fine
    return problems


# ---------------------------------------------------------------- Claude API
def call_claude(data, cfg, feedback=None):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("no ANTHROPIC_API_KEY")
    lo, hi = cfg["bout_lines"]
    user = (f"Write the next Weatherbots bout: {lo}-{hi} lines, about 3-4 minutes read aloud.\n"
            + ("This is the FINAL bout: the storm is over and verified. Award the decision from the scorecard.\n" if data.get("verification") else "")
            + "DATA:\n" + json.dumps(data, indent=1))
    msgs = [{"role": "user", "content": user}]
    if feedback:
        msgs += [{"role": "assistant", "content": [{"type": "text", "text": "Draft submitted."}]},
                 {"role": "user", "content": "The draft failed these checks. Fix every one and resubmit the whole bout:\n- " + "\n- ".join(feedback[:40])}]
    body = dict(model=cfg["model"], max_tokens=cfg["max_output_tokens"], system=SYSTEM, messages=msgs,
                tools=[TOOL], tool_choice={"type": "tool", "name": "submit_bout"})
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        resp = json.loads(r.read())
    for blk in resp.get("content", []):
        if blk.get("type") == "tool_use" and blk.get("name") == "submit_bout":
            usage = resp.get("usage", {})
            log("claude usage:", usage)
            return blk["input"]
    raise RuntimeError("no tool_use in response: " + json.dumps(resp)[:400])


# ---------------------------------------------------------------- entry point
def write(state, init, cfg, final=False):
    data = build_data(state, init, final)
    bout, mode, problems = None, None, None
    try:
        b = call_claude(data, cfg)
        problems = check(b, data)
        if problems:
            log("bout check failed, retrying:", problems[:6])
            b = call_claude(data, cfg, feedback=problems)
            problems = check(b, data)
        if not problems:
            bout, mode = b, "claude"
        else:
            log("bout still failing checks; using template:", problems[:6])
    except Exception as e:
        log("claude unavailable, using template:", repr(e)[:300])
    if bout is None:
        bout, mode = template.bout(state, init, data, final), "template"
    t = parse_iso(init)
    bid = ("final" if final else f"{t:%Y%m%d%H}")
    bout.update(id=bid, init=init, mode=mode, written=iso(dt.datetime.utcnow()), storm=state["id"])
    write_json(os.path.join(STORMS, state["id"], "bouts", bid + ".json"), bout)
    state["bouts"] = [b for b in state.get("bouts", []) if b["id"] != bid] + [dict(id=bid, init=init, title=bout["title"], mode=mode)]
    used = set(state.get("quotes_used", []))
    for l in bout["lines"]:
        if l.get("screen", "").startswith("quote:"):
            used.add(int(l["screen"].split(":")[1]))
    state["quotes_used"] = sorted(used)
    log(f"bout {bid} written ({mode}, {len(bout['lines'])} lines)")
    return bout
