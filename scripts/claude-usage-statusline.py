#!/usr/bin/env python3
# sliceworks 0.8.8. Claude plan usage readings from the Claude Code status line, the only documented source of the
# subscription windows (https://code.claude.com/docs/en/statusline: `rate_limits.five_hour` and `.seven_day`, each with
# `used_percentage` 0-100 and `resets_at` in Unix epoch seconds; present for Pro and Max after the session's first
# API response, each window possibly absent). No credentials are read.
#
#   statusLine command: python3 -I <this script>      (stdin: the status line JSON; stdout: one status line)
#
# Appends one row in the usage-reading shape (schemas/usage-reading.schema.json, runtime "claude", event "tick") to
# <state dir>/metrics/usage-claude.jsonl of the adopted project the session works in. A separate file because the
# budget guard judges a dispatch by the last row of usage.jsonl whatever its runtime; the dashboard reads both.
# A row is written when a value changed or the last row is older than SW_CLAUDE_READING_MINUTES (default 15).
# Inert, printing the status line only, outside an adopted project or without rate_limits. Never fails the line.
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import sys

FIELDS = ("five_hour_pct", "five_hour_reset", "weekly_pct", "weekly_reset")


def config(root: pathlib.Path) -> dict:
    out = {}
    try:
        text = (root / ".sliceworks" / "config.env").read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        m = re.match(r"^\s*([A-Z][A-Z0-9_]*)=(\"[^\"]*\"|'[^']*'|[^#\s]*)", line)
        if m:
            out[m.group(1)] = m.group(2).strip("\"'")
    return out


def project_root(start: str) -> pathlib.Path | None:
    p = pathlib.Path(start or ".").resolve()
    for d in (p, *p.parents):
        if (d / ".sliceworks" / "config.env").is_file():
            return d
    return None


def window(rl: dict, key: str) -> tuple:
    w = rl.get(key) if isinstance(rl.get(key), dict) else {}
    pct, reset = w.get("used_percentage"), w.get("resets_at")
    pct = pct if isinstance(pct, (int, float)) and not isinstance(pct, bool) and 0 <= pct <= 100 else None
    if isinstance(reset, (int, float)) and not isinstance(reset, bool):
        reset = dt.datetime.fromtimestamp(reset, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        reset = None
    return pct, reset


def last_row(path: pathlib.Path) -> dict:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    for line in reversed(lines):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return {}


def record(data: dict, now: dt.datetime) -> tuple:
    rl = data.get("rate_limits") if isinstance(data.get("rate_limits"), dict) else {}
    five, five_reset = window(rl, "five_hour")
    week, week_reset = window(rl, "seven_day")
    ws = data.get("workspace") if isinstance(data.get("workspace"), dict) else {}
    root = project_root(ws.get("project_dir") or data.get("cwd") or os.getcwd())
    if root is None or (five is None and week is None):
        return five, week
    cfg = config(root)
    path = root / cfg.get("SW_STATE_DIR", "docs/process") / "metrics" / "usage-claude.jsonl"
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    row = {"at": stamp, "event": "tick", "runtime": "claude", "observed_at": stamp,
           "source": "claude statusLine rate_limits", "five_hour_pct": five, "five_hour_reset": five_reset,
           "weekly_pct": week, "weekly_reset": week_reset, "weekly_model_pct": None, "weekly_model": None}
    prev = last_row(path)
    try:
        minutes = int(cfg.get("SW_CLAUDE_READING_MINUTES", "15") or 15)
    except ValueError:
        minutes = 15
    try:
        age = (now - dt.datetime.strptime(prev.get("at", ""), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc))
    except ValueError:
        age = None
    if prev and all(prev.get(k) == row[k] for k in FIELDS) and age is not None and age < dt.timedelta(minutes=minutes):
        return five, week
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as out:
        out.write(json.dumps(row) + "\n")
    return five, week


def main() -> int:
    five = week = None
    model = ""
    try:
        data = json.loads(sys.stdin.read() or "{}")
        if isinstance(data, dict):
            m = data.get("model") if isinstance(data.get("model"), dict) else {}
            model = str(m.get("display_name") or "")
            five, week = record(data, dt.datetime.now(dt.timezone.utc))
    except Exception:  # the status line must never break the session
        pass
    parts = [model] if model else []
    parts += [f"5h {five:.0f}%" if five is not None else "5h —", f"7d {week:.0f}%" if week is not None else "7d —"]
    print(" · ".join(parts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
