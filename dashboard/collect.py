# sliceworks 0.7.0. Dashboard, collect stage: read the project's files into one snapshot dictionary.
# Every path comes from .sliceworks/config.env (or the --state-dir override); nothing project-specific is written here.
# Reads only. History and caches belong to the command line (dashboard/__main__.py), never to render.
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
from pathlib import Path

SLICE_ID = re.compile(r"slice-\d+[A-Za-z0-9-]*$")


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return ""


def load_config(root: Path) -> dict[str, str]:
    """Flat KEY=value lines of .sliceworks/config.env, quotes and trailing comments removed."""
    out: dict[str, str] = {}
    for line in read(root / ".sliceworks" / "config.env").splitlines():
        m = re.match(r"^\s*([A-Z][A-Z0-9_]*)=(\"[^\"]*\"|'[^']*'|[^#\s]*)", line)
        if m:
            out[m.group(1)] = m.group(2).strip("\"'")
    return out


def section(text: str, heading: str) -> str:
    m = re.search(r"^## " + re.escape(heading) + r".*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1) if m else ""


CELL_SEP = re.compile(r"(?:(?<=\s)|^)\|(?=\s|$)")  # a pipe with space on both sides; `a|b` inside a cell stays


def cells(line: str) -> list[str]:
    s = line.strip()
    s = s[1:] if s.startswith("|") else s
    s = s[:-1] if s.endswith("|") else s
    return [c.strip() for c in CELL_SEP.split(s)]


def table(text: str) -> list[dict[str, str]]:
    """The first Markdown table in text, as dictionaries keyed by the header cells. Empty cells (`| |`) are kept."""
    rows, head = [], None
    for line in text.splitlines():
        if not line.startswith("|"):
            if head is not None and rows:
                break
            continue
        cells_ = cells(line)
        if head is None:
            head = cells_
        elif set(line.replace("|", "").strip()) <= set("-: "):
            continue
        else:
            rows.append(dict(zip(head, cells_ + [""] * (len(head) - len(cells_)))))
    return rows


def kv(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        m = re.match(r"^([a-z_]+): ?(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def split_top(s: str, sep: str) -> list[str]:
    out, depth, cur = [], 0, ""
    for ch in s:
        depth += ch == "("
        depth -= ch == ")"
        if ch == sep and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def parse_iso(v):
    """An aware UTC timestamp from ISO text (Z, offset or none) or integer Unix seconds; None otherwise."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        try:
            return dt.datetime.fromtimestamp(v, tz=dt.timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(v, str) or not v:
        return None
    m = re.search(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?(?:Z|[+-]\d{2}:?\d{2})?", v)
    if not m:
        return None
    s = m.group(0).replace(" ", "T").replace("Z", "+00:00")
    if re.search(r"[+-]\d{4}$", s):
        s = s[:-2] + ":" + s[-2:]
    try:
        parsed = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def jsonl(p: Path) -> list[dict]:
    out = []
    for line in read(p).splitlines():
        if line.strip():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if isinstance(d, dict):
                out.append(d)
    return out


def json_list(p: Path) -> list[dict]:
    try:
        d = json.loads(read(p) or "[]")
    except ValueError:
        return []
    return [x for x in d if isinstance(x, dict)] if isinstance(d, list) else []


def git(root: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def split_id(cell: str) -> tuple[str, str]:
    """'slice-01 land-inflight-set (process)' -> ('slice-01', 'land-inflight-set (process)')."""
    parts = (cell or "").replace("∥", "").strip().split(None, 1)
    return (parts[0], parts[1].strip()) if len(parts) == 2 else ((parts[0], "") if parts else ("", ""))


# ---- state files ----------------------------------------------------------------------------------------------------

def state_md(text: str) -> dict:
    slices = []
    for r in table(section(text, "Slices")):
        sid, name = split_id(r.get("id", ""))
        r["id"], r["name"] = sid, name
        try:
            r["inc"] = int((r.get("increment") or "0").strip() or 0)
        except ValueError:
            r["inc"] = 0
        slices.append(r)
    return {
        "integration": kv(section(text, "Integration")),
        "milestone": kv(section(text, "Milestone")),
        "increment": kv(section(text, "Increment")),
        "slices": slices,
        "contracts": [c for c in table(section(text, "Contracts")) if c.get("id")],
        "holds": [h for h in table(section(text, "Holds")) if h.get("reason")],
        "queued": [l[2:] for l in section(text, "Queued").splitlines() if l.startswith("- ")],
    }


INC_HEADING = re.compile(r"^## Increment (\d+): (.+)$", re.M)
INC_LIKE = re.compile(r"^#{1,6}\s*Increments?\b.*$", re.M | re.I)


def backlog_unparsed(text: str) -> list[str]:
    """Headings that name increments but are not `## Increment <n>: <title>` (a range such as `## Increments 2 to 5`,
    a missing title, another level): the increments under them are invisible to backlog_md, so the page warns."""
    return [m.group(0).strip() for m in INC_LIKE.finditer(text) if not INC_HEADING.fullmatch(m.group(0).strip())]


def inc_set(v) -> set[int]:
    """'3' -> {3}; '0 to 3' -> {0, 1, 2, 3}; '1, 4' -> {1, 4}; 3 -> {3}."""
    if isinstance(v, int) and not isinstance(v, bool):
        return {v}
    v = v if isinstance(v, str) else ""
    out: set[int] = set()
    for a, b in re.findall(r"(\d+)\s*(?:to|-|–)\s*(\d+)", v):
        out |= set(range(int(a), int(b) + 1))
    return out | {int(x) for x in re.findall(r"\d+", v)}


def backlog_md(text: str) -> list[dict]:
    incs = []
    for m in INC_HEADING.finditer(text):
        n, title = int(m.group(1)), m.group(2).strip()
        body = section(text, f"Increment {n}:")
        demo = re.search(r"Exit demo: (.*?)(?: Scenarios:|$)", body, re.S | re.M)
        prop = re.search(r"Proposed slices[^:]*: (.*?)(?:\.\s*$|\n)", body, re.M)
        planned = []
        if prop:
            planned = split_top(prop.group(1), ";")
            if len(planned) == 1:
                planned = split_top(prop.group(1), ",")
        titles, states = {}, {}
        for r in table(body):
            sid, name = split_id(r.get("slice", ""))
            if SLICE_ID.match(sid):
                titles[sid] = name
                states[sid] = r.get("state", "")
        if not planned:
            planned = [f"{sid} {t}".strip() for sid, t in titles.items()]
        incs.append({"n": n, "title": title, "demo": demo.group(1).strip() if demo else "",
                     "planned": planned, "titles": titles})
    return incs


def milestones_md(text: str) -> list[dict]:
    out = []
    for m in re.finditer(r"^## (M\d+)\s*[·:-]\s*(.+)$", text, re.M):
        mid, title = m.group(1), m.group(2).strip()
        body = section(text, f"{mid} ")
        st = re.search(r"^State:\s*(.+)$", body, re.M)
        incs = []
        for r in table(body.split("### Increments", 1)[1] if "### Increments" in body else ""):
            try:
                n = int(re.match(r"\s*(\d+)", r.get("n", "")).group(1))
            except (AttributeError, ValueError):
                continue
            incs.append({"n": n, "title": r.get("title", ""), "demo": r.get("exit demo", ""), "state": r.get("state", "")})
        gates = [g for g in table(body.split("### Gate families", 1)[1] if "### Gate families" in body else "")
                 if g.get("family")]
        out.append({"id": mid, "title": title, "state": (st.group(1).strip() if st else ""), "increments": incs, "gates": gates})
    return out


def decisions_md(text: str) -> list[dict]:
    """### <id> · <title> entries with their first metadata line: date, origin, class, status, veto by, due, default."""
    out = []
    for m in re.finditer(r"^### ([A-Z]+-[A-Za-z0-9-]+)\s*·\s*(.+?)\n- (.+)$", text, re.M):
        did, title, meta = m.group(1), m.group(2).strip(), m.group(3)
        if "<" in did or "<title>" in title:
            continue
        cls = re.search(r"class (A1|A2|M|B)\b", meta)
        status = re.search(r"\*\*([a-z]+)\*\*", meta)
        veto = re.search(r"veto by (\d{4}-\d{2}-\d{2})", meta)
        due = re.search(r"due (\d{4}-\d{2}-\d{2}|[^·]+?)\s*(?:·|$)", meta)
        default = re.search(r"default at due: (.*?)(?: · \*\*|$)", meta)
        out.append({"id": did, "title": title, "class": cls.group(1) if cls else "",
                    "status": status.group(1) if status else "", "veto_by": veto.group(1) if veto else "",
                    "due": due.group(1).strip() if due else "", "default": default.group(1).strip() if default else "",
                    "question": bool(re.match(r"[A-Z]*Q-", did)), "pivot": "pivot" in meta})
    return out


def needs_md(text: str) -> list[dict]:
    rows = [r for r in table(text.replace(" || ", " | ")) if re.match(r"[A-Z]+-\d+", r.get("id", ""))]
    for r in rows:  # the header is "act (what to do, ...)"; normalise to "act"
        r["act"] = next((v for k, v in r.items() if k.startswith("act")), "")
        r["open"] = r.get("done", "").strip() in ("", "-", "no", "open")
    return rows


def progress_md(text: str, n: int = 4) -> list[str]:
    return [l[3:] for l in text.splitlines() if l.startswith("## ") and not l.startswith("## <")][-n:][::-1]


# ---- agent counters (linked metadata only; absent coverage stays UNKNOWN) ---------------------------------------------

EXPECTED_RUNTIMES = ("claude", "codex")


def _count(v) -> int | None:
    if isinstance(v, bool) or not isinstance(v, int):
        return None
    return v if v >= 0 else None


def usage_components(usage) -> dict | None:
    """Preserve known counters without inventing cache coverage or double-counting reasoning."""
    if not isinstance(usage, dict):
        return None
    inp = _count(usage.get("input_tokens"))
    cached = _count(usage.get("cached_input_tokens"))
    out = _count(usage.get("output_tokens"))
    includes_cached = usage.get("input_includes_cached") if isinstance(usage.get("input_includes_cached"), bool) else None
    fresh_input = None
    if inp is not None and cached is not None and includes_cached is True and cached <= inp:
        fresh_input = inp - cached
    elif inp is not None and cached is not None and includes_cached is False:
        fresh_input = inp
    elif inp is not None and cached == 0:
        fresh_input = inp
    tokens = fresh_input + out if fresh_input is not None and out is not None else None
    return {"input": fresh_input, "input_reported": inp, "cached_input": cached, "output": out,
            "tokens": tokens, "partial": tokens is None}


def _native_counter_events(path: Path, label: str):
    """Counter-only Codex events from a per-slice native log (<outputs>/slices/<slice>/codex/<role>-*.jsonl)."""
    thread_id = None
    for line_no, line in enumerate(read(path).splitlines(), 1):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "thread.started" and isinstance(event.get("thread_id"), str):
            thread_id = event["thread_id"]
            continue
        started = (event.get("thread") or {}).get("started") if isinstance(event.get("thread"), dict) else event.get("thread.started")
        if isinstance(started, dict) and isinstance(started.get("thread_id"), str):
            thread_id = started["thread_id"]
            continue
        completed = (event.get("turn") or {}).get("completed") if isinstance(event.get("turn"), dict) else event.get("turn.completed")
        if not isinstance(completed, dict) and event.get("type") == "turn.completed":
            completed = {"turn_id": event.get("turn_id"), "timestamp": event.get("timestamp"), "usage": event.get("usage")}
        if not isinstance(completed, dict) or not isinstance(completed.get("usage"), dict) or not thread_id:
            continue
        yield {"runtime": "codex", "physical_source": label, "session_id": thread_id,
               "turn_id": str(completed.get("turn_id") or line_no), "timestamp": completed.get("timestamp", event.get("timestamp", "")),
               "role": path.stem.rsplit("-", 1)[0], "slice": path.parent.parent.name, "usage": completed["usage"]}


def agent_usage(root: Path, run_dir: Path, outputs_dir: Path) -> tuple[list[dict], dict]:
    records: dict[tuple, dict] = {}
    sources, runtimes, partial = set(), set(), False
    paths = [run_dir / "agent-usage-events.jsonl"] + sorted((outputs_dir / "slices").glob("*/codex/*.jsonl"))
    for path in paths:
        if "/codex/" in path.as_posix():
            try:
                label = str(path.relative_to(root))
            except ValueError:
                label = str(path)
            events = _native_counter_events(path, label)
        else:
            events = jsonl(path)
        for event in events:
            runtime = str(event.get("runtime", "")).lower()
            source, session, turn = event.get("physical_source"), event.get("session_id"), event.get("turn_id")
            comp = usage_components(event.get("usage"))
            stamp = parse_iso(event.get("timestamp", ""))
            if runtime not in EXPECTED_RUNTIMES or not all(isinstance(x, str) and x for x in (source, session, turn)) or not comp:
                continue
            key = (source, runtime, session, turn)
            cand = {"slice": event.get("slice"), "role": str(event.get("role", "agent")), "runtime": runtime,
                    "start": stamp.isoformat() if stamp else "", "end": stamp.isoformat() if stamp else "",
                    "active_s": _count(event.get("active_seconds")), **comp}
            old = records.get(key)
            if old and event.get("cumulative") is True and all(
                    isinstance(cand[k], int) and isinstance(old[k], int) and cand[k] >= old[k] for k in ("input", "cached_input", "output")):
                records[key] = cand
            elif not old:
                records[key] = cand
            sources.add(source); runtimes.add(runtime); partial |= cand["partial"] or stamp is None
    out = list(records.values())
    missing = [x for x in EXPECTED_RUNTIMES if x not in runtimes]
    detail = "linked counter metadata" if out else "no linked runtime usage metadata"
    if missing:
        detail += f"; {', '.join(missing)} runtime UNKNOWN"
    if partial:
        detail += "; incomplete counter/time coverage UNKNOWN"
    return out, {"state": "PARTIAL" if out or missing else "UNKNOWN", "detail": detail}


def slice_activity(root: Path, outputs_dir: Path, slices: list[dict], events: list[dict]) -> dict[str, tuple[float, str]]:
    """Latest activity (epoch seconds, source) per active or repairing slice: agent counters, branch commit, tier log."""
    out = {}
    for x in slices:
        if x.get("state") not in ("active", "repair"):
            continue
        best, src = 0.0, "nothing"
        for a in events:
            t = parse_iso(a.get("end"))
            if a.get("slice") == x["id"] and t and t.timestamp() > best:
                best, src = t.timestamp(), "agent counters"
        if x.get("branch") and x["branch"] not in ("-",):
            c = git(root, "log", "-1", "--format=%ct", x["branch"])
            if c.isdigit() and int(c) > best:
                best, src = float(c), "commit"
        logs = outputs_dir / "slices" / x["id"]
        if logs.is_dir():
            m = max((p.stat().st_mtime for p in logs.rglob("*") if p.is_file()), default=0.0)
            if m > best:
                best, src = m, "tier log"
        out[x["id"]] = (best, src)
    return out


# ---- the snapshot ---------------------------------------------------------------------------------------------------

def snapshot(root: Path, cfg: dict[str, str], state_dir: Path | None = None) -> dict:
    root = root.resolve()
    S = state_dir or (root / cfg.get("SW_STATE_DIR", "docs/process"))
    run_dir = root / cfg.get("SW_RUN_DIR", ".run")
    outputs_dir = root / cfg.get("SW_OUTPUTS_DIR", "outputs")
    state = state_md(read(S / "STATE.md"))
    usage_rows = jsonl(S / "metrics" / "usage.jsonl")
    money_file = root / cfg["SW_MONEY_FILE"] if cfg.get("SW_MONEY_FILE") else S / "metrics" / "money.jsonl"
    decisions = decisions_md(read(S / "DECISIONS.md"))
    for d in decisions_md(read(S / "OWNER-DECISIONS.md")):
        decisions.append(d)
    scen_path = S / "SCENARIOS.json" if (S / "SCENARIOS.json").exists() else S / "scenarios.json"
    events, coverage = agent_usage(root, run_dir, outputs_dir)
    head = git(root, "log", "-1", "--format=%h %s")
    title = re.search(r"^# (.{1,40})$", read(root / "README.md"), re.M)
    return {
        "root": str(root),
        "name": cfg.get("SW_PROJECT_NAME") or (title.group(1).strip() if title else root.name),
        "state_dir": str(S),
        "config": cfg,
        "head": head,
        **state,
        "backlog": backlog_md(read(S / "BACKLOG.md")),
        "backlog_unparsed": backlog_unparsed(read(S / "BACKLOG.md")),
        "milestones": milestones_md(read(S / "MILESTONES.md")),
        "features": json_list(S / "FEATURES.json"),
        "scenarios": json_list(scen_path),
        "needs": needs_md(read(S / "NEEDS-HUMAN.md")),
        "decisions": decisions,
        "usage": usage_rows[-1] if usage_rows else {},
        "money": jsonl(money_file),
        "tiers": jsonl(S / "metrics" / "tiers.jsonl"),
        "progress": progress_md(read(S / "PROGRESS.md")),
        "retros": sorted(p.name for p in (S / "retros").glob("increment-*.md")),
        "agent_events": events,
        "agent_coverage": coverage,
        "activity": slice_activity(root, outputs_dir, state["slices"], events),
    }
