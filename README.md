# Weatherbots

Three cartoon robots argue about who's right when a big snowstorm is coming:
**Big Gus** (the GFS), **Eccy the Euro** (ECMWF, with his AI little brother, the AIFS), and **Little Nammy** (the NAM).
A referee, **The Blend**, keeps score. Every number and every WPC quote comes from the real model data and WPC's own products.

**Site:** https://richmamrosh-source.github.io/weatherbots/

## How it works

Twice a day (08:40 and 20:40 UTC, after the 00z and 12z runs are published), a GitHub Actions job:

1. **Watches WPC.** Reads WPC's 2.5 km probabilistic snowfall forecast (Days 1–3). A storm opens when the area with a
   ≥40% chance of 8"+ in 24 hours exceeds 40,000 km². Settings are in `config.json`.
2. **Backfills the run-up.** When a storm opens, it pulls every 00z and 12z GFS, ECMWF IFS, ECMWF AIFS and NAM run
   going back 6.5 days from public archives (NOAA Open Data on AWS, ECMWF open data), so the first bout already covers the whole history.
3. **Scores each cycle.** For every run it tracks the surface low, takes its position and pressure at the storm's
   target time, its liquid at ~10 cities, and its 500 mb heights. While the storm is live, runs are compared with the
   consensus of the other models.
4. **Writes a bout.** Claude (Opus 5.5 by default) writes a 3–4 minute script from those numbers, the bots' known
   biases, the latest WPC discussion quotes, and what the bots said last time. A checker rejects any number that
   isn't in the data, any spelled-out number, and any screen that doesn't exist. If the check fails twice, or the
   API is unavailable, a template bout is written instead, so the site never goes dark.
5. **Verifies.** About 30 hours after the snow ends, it scores every run against the analyzed low (GFS + ECMWF
   analyses), Stage IV precipitation and NWS climate-report snowfall, builds a scorecard by lead time, and writes a
   final bout with the decision.

Everything the page shows is in `site/data/`, committed back to this repository after each run.

## Running it by hand

**Actions → Weatherbots → Run workflow**, then pick a command:

| Command | What it does |
|---|---|
| `cycle` | The normal scheduled job. |
| `rewrite-bout` | Rewrites one bout with Claude. Storm: `2026-02-23-northeast`. Args: `--init 2026-02-20T00Z` (a cycle) or `--final`. Good for testing your API key on the archived blizzard. |
| `open-storm` | Opens a storm manually, e.g. args `--target 2026-12-20T12Z --bbox=-78,38,-69,45 --start 2026-12-20T00Z --end 2026-12-21T12Z --region Northeast` |
| `deploy-only` | Republishes the site without running anything. |

On your own machine (Linux/macOS, Python 3.11+): `pip install -r requirements.txt`, then `python run.py cycle`.
Set `ANTHROPIC_API_KEY` to get Claude-written bouts.

## Settings (`config.json`)

- `model`: the Claude model that writes bouts (`claude-opus-5-5`; `claude-fable-5-1` for a livelier, pricier script)
- `bout_lines`: target script length
- `wpc`: storm-opening thresholds
- `backfill_days`, `close_after_hours`, `stations_per_storm`

## Cost

Each Claude bout uses about 10k input and 5k output tokens, roughly 15 cents on Opus 5.5. Two per day during an
active storm. GitHub Actions and Pages are free for public repositories.

## Known limits

- WPC's machine-readable snow probabilities go out 3 days, so storms open about 3 days ahead (the backfill covers
  the earlier runs).
- The tracker follows the deepest surface low in the storm's domain at the target time. That's right for
  nor'easters and most Plains cyclones; a storm with two competing lows can confuse it.
- Liquid, not snowfall, is compared across models. Snowfall depends on ratios the models handle differently.
- The number checker blocks numbers that appear nowhere in the data, but it cannot tell if a real number is used
  with the wrong unit.

## Layout

```
run.py                 entry point (cycle, open, bout)
config.json            settings
wb/wpc.py              WPC probability watcher
wb/fields.py           GRIB byte-range downloads (GFS, NAM, IFS, AIFS)
wb/track.py            surface-low tracking, sampling, regridding
wb/cycle.py            per-cycle scoring
wb/discuss.py          WPC discussion quotes (IEM AFOS archive)
wb/verify.py           analysis, Stage IV, climate reports, scorecard
wb/bout.py             Claude bout writer + number checker
wb/template.py         fallback bout
wb/casefile.py         the case.json the page reads
site/index.html        the Weatherbots page
site/data/             storms, bouts and case files (written by the job)
```
