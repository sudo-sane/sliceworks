# sliceworks 0.7.0. Dashboard, compute stage: pure functions from a snapshot to the numbers the page shows.
# A number the data cannot support is UNKNOWN or left out, never a silent zero.
from __future__ import annotations

import datetime as dt
import re

from .collect import SLICE_ID, inc_set, parse_iso

# The slice-state vocabulary, defined once: state -> (stepper stage, colour kind, progress credit). It holds every
# state of method chapter 3's slice lifecycle plus older spellings (review, testing, draft); check-design-docs.py
# lints STATE.md and BACKLOG.md against it. Stage indexes STAGES below (-1: not started). Credit is the share of one
# slice-equivalent; None leaves the slice out of the progress total (cut work). "merged" earns 1.0 once its green
# (T2) timestamp is recorded.
STAGES = [("ready", "Brief ready"), ("active", "Implementing"), ("candidate", "Candidate"),
          ("review_pass", "Review passed"), ("merged", "Merged"), ("green", "T2 green")]
STATES: dict[str, tuple[int, str, float | None]] = {
    "proposed": (-1, "idle", 0.0), "draft": (-1, "idle", 0.0), "ready": (0, "ready", 0.05),
    "active": (1, "work", 0.25), "blocked": (1, "bad", 0.25), "paused": (1, "warn", 0.25), "hold": (1, "warn", 0.25),
    "repair": (1, "warn", 0.5), "testing": (2, "work", 0.5), "candidate": (2, "work", 0.5),
    "review": (3, "work", 0.6), "in_review": (3, "work", 0.6), "waiting": (3, "ready", 0.5),
    "merged": (5, "done", 0.9), "green": (5, "done", 1.0), "accepted": (5, "done", 1.0),
    "blocked_on_human": (-1, "warn", 0.0),
    "plan_review": (-1, "ready", 0.0), "contract_hold": (-1, "warn", 0.0), "source_hold": (-1, "warn", 0.0),
    "stopped": (-1, "idle", 0.0), "cut": (-1, "idle", None), "dropped": (-1, "idle", None), "superseded": (-1, "idle", None),
}
DONE_STATES = ("merged", "green", "accepted", "waiting")
LIVE_STATES = ("active", "repair", "blocked", "testing")
# Credit reached by a timestamp column, for the budget burn since the last weekly reset.
STAMP_CREDIT = (("ready", 0.05), ("active", 0.25), ("candidate", 0.6), ("review_pass", 0.6), ("merged", 0.9), ("green", 1.0))


def norm_state(s: str) -> str:
    return (s or "").strip().lower()


def known(state: str) -> bool:
    return norm_state(state) in STATES


def kind_of(state: str) -> str:
    st = norm_state(state)
    return STATES[st][1] if st in STATES else "unknown"


def stage_of(state: str) -> int:
    return STATES.get(norm_state(state), (-1, "", 0.0))[0]


def stamped(v) -> bool:
    return v not in ("", "-", None)


def credit(x: dict) -> float | None:
    st = norm_state(x.get("state", ""))
    if st == "merged":
        return 1.0 if stamped(x.get("green")) else STATES["merged"][2]
    return STATES.get(st, (0, "", 0.0))[2]


def credit_at(x: dict, t: dt.datetime) -> float:
    best = 0.0
    for key, c in STAMP_CREDIT:
        ts = parse_iso(x.get(key, ""))
        if ts and ts <= t:
            best = max(best, c)
    return best


def zone(name: str) -> dt.tzinfo:
    """SW_TIMEZONE: an IANA name, UTC, or a fixed offset such as +03:00 or UTC+3."""
    name = (name or "UTC").strip()
    m = re.fullmatch(r"(?:UTC|GMT)?\s*([+-])(\d{1,2})(?::?(\d{2}))?", name)
    if m:
        off = dt.timedelta(hours=int(m.group(2)), minutes=int(m.group(3) or 0)) * (1 if m.group(1) == "+" else -1)
        return dt.timezone(off, name)
    if name.upper() in ("UTC", "Z", "GMT"):
        return dt.timezone.utc
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        return dt.timezone.utc


def pct_int(v, default: int) -> int:
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return default
    return n if 0 <= n <= 100 else default


def thresholds(cfg: dict, rt: str = "") -> dict[str, int]:
    """Hold and stop lines; SW_<RUNTIME>_WEEKLY_DISPATCH_HOLD and _STOP override the weekly pair for one runtime."""
    hold, stop = pct_int(cfg.get("SW_WEEKLY_DISPATCH_HOLD"), 80), pct_int(cfg.get("SW_WEEKLY_STOP"), 85)
    if rt:
        hold = pct_int(cfg.get(f"SW_{rt.upper()}_WEEKLY_DISPATCH_HOLD"), hold)
        stop = pct_int(cfg.get(f"SW_{rt.upper()}_WEEKLY_STOP"), stop)
    return {"hold": hold, "stop": stop,
            "hold5": pct_int(cfg.get("SW_FIVE_HOUR_DISPATCH_HOLD"), 90), "stop5": pct_int(cfg.get("SW_FIVE_HOUR_STOP"), 100)}


def slices_of(snap: dict, n: int | None = None) -> list[dict]:
    return [x for x in snap["slices"] if SLICE_ID.match(x.get("id", "")) and (n is None or x.get("inc", 0) == n)]


def rows_of(features: list[dict], pred) -> tuple[list[dict], int, int]:
    rs = [f for f in features if pred(f)]
    return rs, sum(1 for f in rs if f.get("passes") is True), sum(1 for f in rs if f.get("passes") is not True and f.get("human_act"))


def row_inc(f: dict) -> int | None:
    """A FEATURES.json row's increment as an integer (3 or "3"); None when absent or unreadable."""
    v = f.get("increment")
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    return int(v) if isinstance(v, str) and v.strip().isdigit() else None


def closed_text(state: str) -> bool:
    return bool(re.match(r"(closed|done|accepted)", (state or "").strip().lower()))


def increments(snap: dict) -> list[dict]:
    """Every increment the project knows about, whatever its state: the BACKLOG.md sections, every row of the
    MILESTONES.md increments tables, every FEATURES.json increment and every NEEDS-HUMAN.md increment number.
    One without a BACKLOG section is rendered from what is known (no_section, with its sources). A closed MILESTONES
    increment numbered below every BACKLOG section, and without one, was closed before adoption (before)."""
    ms_inc: dict[int, dict] = {}
    for m in snap["milestones"]:
        for i in m["increments"]:
            ms_inc.setdefault(i["n"], dict(i, milestone=m["id"]))
    incs = [dict(i, milestone=ms_inc.get(i["n"], {}).get("milestone", ""), before=False, no_section=False)
            for i in snap["backlog"]]
    have = {i["n"] for i in incs}
    first = min(have, default=None)
    sources: dict[int, list[str]] = {}
    for n in ms_inc:
        sources.setdefault(n, []).append("MILESTONES.md")
    for n in sorted({row_inc(f) for f in snap["features"]} - {None}):
        sources.setdefault(n, []).append("FEATURES.json")
    for n in sorted({k for r in snap["needs"] for k in inc_set(r.get("increment", ""))}):
        sources.setdefault(n, []).append("NEEDS-HUMAN.md")
    for n in sorted(set(sources) - have):
        mi = ms_inc.get(n, {})
        closed = closed_text(mi.get("state", ""))
        before = closed and (first is None or n < first)
        incs.append({"n": n, "title": mi.get("title", ""), "demo": mi.get("demo", ""), "planned": [], "titles": {},
                     "milestone": mi.get("milestone", ""), "before": before, "no_section": not before,
                     "closed": closed, "state_text": mi.get("state", ""), "sources": sources[n]})
    return sorted(incs, key=lambda i: (not i["before"], i["n"]))


def unsized(snap: dict, incs: list[dict]) -> list[dict]:
    """Increments with neither slice rows in STATE.md nor proposed slices in BACKLOG.md: their size is unknown, so
    progress() leaves them out of the percentage rather than counting a guessed slice, and the tile says so."""
    return [i for i in incs if not i["before"] and not i["planned"]
            and not [x for x in slices_of(snap, i["n"]) if credit(x) is not None]]


def progress(snap: dict, incs: list[dict], cur_n: int) -> list[tuple[int, str, float, float]]:
    """(n, title, total, done) in slice-equivalents for every sized increment; earlier closed ones count as done.
    Increments closed before adoption and unsized ones (see unsized()) are left out."""
    per = []
    skip = {i["n"] for i in unsized(snap, incs)}
    for inc in incs:
        if inc["before"] or inc["n"] in skip:
            continue
        mine = [x for x in slices_of(snap, inc["n"]) if credit(x) is not None]
        if mine:
            per.append((inc["n"], inc["title"], float(len(mine)), sum(credit(x) for x in mine)))
        elif inc["n"] < cur_n:
            k = float(len(inc["planned"]))
            per.append((inc["n"], inc["title"], k, k))
        else:
            per.append((inc["n"], inc["title"], float(len(inc["planned"])), 0.0))
    return per


def fmt_eta(hours: float) -> str:
    return f"ETA ≈{hours / 24:.0f} d" if hours > 36 else f"ETA ≈{hours:.0f} h"


def pace(snap: dict, per: list, now: dt.datetime) -> dict:
    """Slice-equivalents per wall-clock hour since the first slice was ready; an ETA only after three are done."""
    done = sum(d for _, _, _, d in per)
    total = sum(t for _, _, t, _ in per) or 1.0
    starts = [t for x in slices_of(snap) for t in (parse_iso(x.get("ready", "")), parse_iso(x.get("active", ""))) if t]
    out = {"eta": "", "inc_eta": {}, "rate": 0.0}
    if not starts:
        return out
    hours = max((now - min(starts)).total_seconds() / 3600, 0.1)
    rate = sum(credit(x) or 0 for x in slices_of(snap)) / hours
    out["rate"] = rate
    if done >= 3 and rate > 0:
        cum = 0.0
        for n, _, t, d in sorted(per):
            cum += max(t - d, 0)
            out["inc_eta"][n] = "done" if t - d <= 0.001 else fmt_eta(cum / rate)
        out["eta"] = fmt_eta((total - done) / rate)
    return out


def delta(history: list[dict], prog: float, now: dt.datetime, tz: dt.tzinfo) -> dict | None:
    if len(history) < 2:
        return None
    cutoff = now - dt.timedelta(hours=24)
    base = next((h for h in history if (parse_iso(h.get("t")) or now) >= cutoff), history[0])
    since = parse_iso(base.get("t")) or now
    when = "24 h" if since <= cutoff + dt.timedelta(minutes=5) else since.astimezone(tz).strftime("%H:%M")
    pts = "; ".join(f'{(parse_iso(h.get("t")) or now).astimezone(tz).strftime("%d.%m %H:%M")} {h.get("p", 0):.1f}%' for h in history[-8:])
    return {"delta": prog - float(base.get("p", 0)), "when": when, "points": pts}


def budget_runtimes(snap: dict) -> list[tuple[str, dict]]:
    """(runtime, latest reading) per runtime with a reading; the dual profile always shows claude and codex, so a
    runtime without readings is visible. Without any named reading: one unnamed entry from usage.jsonl."""
    by_rt = snap.get("usage_by_runtime") or {}
    names = set(by_rt) | ({"claude", "codex"} if snap["config"].get("SW_PROFILE") == "dual" else set())
    return [(rt, by_rt.get(rt, {})) for rt in sorted(names)] or [("", snap["usage"])]


def budget(snap: dict, per: list, now: dt.datetime, usage: dict | None = None, rt: str = "") -> dict:
    """Weekly window: used, thresholds, and a forecast of what the rest of the backlog costs at this week's burn."""
    usage, th = snap["usage"] if usage is None else usage, thresholds(snap["config"], rt)
    w = usage.get("weekly_pct")
    out = {"known": isinstance(w, (int, float)) and not isinstance(w, bool), "used": float(w or 0),
           "five": usage.get("five_hour_pct"), "reset": parse_iso(usage.get("weekly_reset")),
           "reset5": parse_iso(usage.get("five_hour_reset")), "at": parse_iso(usage.get("at")), "lines": [], "fc": None, **th}
    used, stop = out["used"], th["stop"]
    out["kind"] = "bad" if used >= stop else "warn" if used >= th["hold"] else ""
    if not out["reset"] or not out["known"]:
        return out
    prev = out["reset"] - dt.timedelta(days=7)
    sl = [x for x in slices_of(snap) if credit(x) is not None]
    done_since = sum(credit(x) for x in sl) - sum(credit_at(x, prev) for x in sl)
    hours_since = max((now - prev).total_seconds() / 3600, 0.1)
    room = max(stop - used, 0)
    total = sum(t for _, _, t, _ in per)
    done = sum(d for _, _, _, d in per)
    if done_since >= 0.5 and used > 0:
        per_slice = used / done_since
        remaining = total - done
        need = remaining * per_slice
        per_hour = used / hours_since
        if need <= room:
            out["lines"].append(f"backlog needs ≈{need:.0f}% more: done at ≈{used + need:.0f}% of the week (stop {stop}%)")
        else:
            afford = room / per_slice
            cum, reach = 0.0, None
            for n, _, t, d in sorted(per):
                cum += max(t - d, 0)
                if cum <= afford + 1e-6:
                    reach = n
            out["lines"].append(f"budget to the stop line covers ≈{afford:.0f} of {remaining:.0f} remaining slices: "
                                f"backlog ≈{100 * (done + afford) / (total or 1):.0f}%" + (f", through increment {reach}" if reach is not None else ""))
        if per_hour > 0:
            out["lines"].append(f"≈{per_slice:.1f}% per slice · ≈{room / per_hour:.0f} h of work left this week at today's burn")
        end = used + need
        out["fc"] = {"need": need, "end": end, "spare": stop - end, "fits": end <= stop, "per_slice": per_slice,
                     "remaining": remaining, "hours_left": room / per_hour if per_hour > 0 else 0.0,
                     "reach_pct": 100 * (done + room / per_slice) / (total or 1)}
    else:
        out["lines"].append("forecast after the first slices of this week finish")
    return out


def ready_now(snap: dict) -> dict:
    """Draft or ready slices whose hard dependencies are merged and whose human acts are done; the writer cap."""
    sl = slices_of(snap)
    state = {x["id"]: norm_state(x.get("state")) for x in sl}
    open_nh = {r["id"] for r in snap["needs"] if r.get("open")}
    writing = [x for x in sl if norm_state(x.get("state")) in ("active", "repair", "review", "in_review", "testing")]
    try:
        cap = int(snap["config"].get("SW_WRITER_CAP", "") or 0)
    except ValueError:
        cap = 0
    ready = []
    for x in sl:
        if norm_state(x.get("state")) not in ("draft", "ready"):
            continue
        deps = [d.strip() for d in re.split(r"[,;]", x.get("depends_hard", "")) if d.strip() and d.strip() not in ("-", "none")]
        blocked = [d for d in deps if (SLICE_ID.match(d) and state.get(d) not in DONE_STATES) or d in open_nh]
        if not blocked:
            ready.append(f'{x["id"]} [{norm_state(x.get("state"))}]')
    return {"ready": ready, "writers": len(writing), "cap": cap}


def scenario_status(s: dict, frow: dict) -> str:
    if str(s.get("status", "")).lower() == "thinned":
        return "thinned"
    ids = s.get("proves") or []
    n = sum(1 for rid in ids if frow.get(rid, {}).get("passes") is True)
    return "proven" if ids and n == len(ids) else "progress" if n else "todo"


def veto_clocks(snap: dict, now: dt.datetime, tz: dt.tzinfo) -> list[dict]:
    """Defaulted or recommended A2, B and M entries whose veto window is still open, soonest first."""
    today = now.astimezone(tz).date()
    out = []
    for d in snap["decisions"]:
        if d["question"] or d["status"] not in ("defaulted", "recommended") or not d["veto_by"]:
            continue
        try:
            by = dt.date.fromisoformat(d["veto_by"])
        except ValueError:
            continue
        left = (by - today).days
        if left >= 0:
            out.append({**d, "left": left})
    return sorted(out, key=lambda d: (d["left"], d["id"]))


def open_questions(snap: dict) -> list[dict]:
    return [d for d in snap["decisions"] if d["question"] and d["status"] == "open"]


def money(snap: dict) -> dict | None:
    try:
        cap = float(snap["config"].get("SW_MONEY_CAP", "0") or 0)
    except ValueError:
        cap = 0.0
    cur = snap["config"].get("SW_MONEY_CURRENCY", "USD")
    rows = [r for r in snap["money"] if isinstance(r.get("amount"), (int, float)) and not isinstance(r.get("amount"), bool)]
    if cap <= 0 and not rows:
        return None
    other = sorted({r.get("currency") for r in rows if r.get("currency") not in (None, cur)})
    spent = sum(float(r["amount"]) for r in rows if r.get("currency") in (None, cur))
    return {"cap": cap, "spent": spent, "left": cap - spent, "currency": cur, "entries": len(rows), "other": other,
            "kind": "bad" if cap and spent >= cap else "warn" if cap and spent >= 0.8 * cap else ""}


def unknown_states(snap: dict) -> list[str]:
    return sorted({x.get("state", "") for x in slices_of(snap) if not known(x.get("state", ""))})
