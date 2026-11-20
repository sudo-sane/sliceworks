#!/usr/bin/env python3
"""Summarize an existing check log; never run checks or certify acceptance."""

from __future__ import annotations

import argparse
from collections import Counter, deque
import hashlib
import json
from pathlib import Path
import re
import sys

from automation_errors import (AutomationError, ErrorLoggingArgumentParser,
                               default_error_log, option_value, report_error)


class AnalysisError(AutomationError):
    """The log is not a complete supported protocol stream."""


SUPPORTED_ACTIONS = {"start", "run", "pause", "cont", "output", "pass", "fail", "skip"}


def summarize(log: Path | str, format_name: str, exit_code: int | None) -> dict:
    """Return bounded observed counts or fail immediately on invalid Go JSON."""
    if format_name not in {"go-json", "go-text"}:
        raise AnalysisError("unsupported summary format: " + str(format_name))
    counts = {kind: Counter() for kind in ("tests", "subtests", "packages")}
    active: set[tuple[str, str]] = set()
    failures: list[dict] = []
    failure_count = lines = 0
    contexts: dict[tuple[str, str], deque[str]] = {}
    tail: deque[str] = deque(maxlen=6)
    digest = hashlib.sha256()

    def terminal(kind: str, status: str, name: str) -> None:
        nonlocal failure_count
        counts[kind][status] += 1
        if status == "fail":
            failure_count += 1
            if len(failures) < 8:
                failures.append({"kind": kind, "name": name[:200]})

    with Path(log).open("rb") as stream:
        for raw in stream:
            digest.update(raw)
            lines += 1
            line = raw.decode("utf-8", errors="replace").rstrip()
            tail.append(line[:200])
            if format_name == "go-text":
                match = re.match(r"^\s*--- (PASS|FAIL|SKIP): (\S+)", line)
                if match:
                    name = match[2]
                    terminal("subtests" if "/" in name else "tests", match[1].lower(), name)
                match = re.match(r"^(ok|FAIL|\?)\s+(\S+)", line)
                if match and match[2] != "FAIL":
                    terminal("packages", {"ok": "pass", "FAIL": "fail", "?": "no_tests"}[match[1]], match[2])
                continue
            try:
                event = json.loads(line)
            except ValueError as exc:
                raise AnalysisError("malformed Go JSON event at log line " + str(lines)) from exc
            if not isinstance(event, dict):
                raise AnalysisError("unsupported non-object Go JSON event at log line " + str(lines))
            action, package, test = event.get("Action"), event.get("Package", ""), event.get("Test", "")
            if not isinstance(action, str) or action not in SUPPORTED_ACTIONS:
                raise AnalysisError("unsupported Go JSON action at log line " + str(lines))
            if not isinstance(package, str) or not isinstance(test, str):
                raise AnalysisError("unsupported Go JSON event fields at log line " + str(lines))
            key = (package, test)
            if action in {"start", "run"}:
                active.add(key)
            elif action == "output":
                output = event.get("Output", "")
                if not isinstance(output, str):
                    raise AnalysisError("unsupported Go JSON output at log line " + str(lines))
                if key in active:
                    contexts.setdefault(key, deque(maxlen=3)).append(output[:200].rstrip())
            elif action in {"pass", "fail", "skip"}:
                if test and key not in active:
                    raise AnalysisError("Go JSON test ended without a start at log line " + str(lines))
                kind = "subtests" if "/" in test else "tests" if test else "packages"
                before = len(failures)
                terminal(kind, action, package + (":" + test if test else ""))
                if len(failures) > before:
                    failures[-1]["diagnostics"] = list(contexts.get(key, ()))
                active.discard(key)
                contexts.pop(key, None)
    if format_name == "go-json" and active:
        sample = ", ".join((package + (":" + test if test else ""))[:200] for package, test in sorted(active)[:3])
        raise AnalysisError("incomplete Go JSON terminal protocol for " + sample)
    process_status = "unknown" if exit_code is None else "passed" if exit_code == 0 else "failed"
    result = {
        "schema_version": 2, "process_status": process_status, "recorded_exit_code": exit_code,
        "format": format_name, "log": str(Path(log).resolve()), "log_sha256": digest.hexdigest(),
        "log_lines": lines, "counts": {kind: dict(value) for kind, value in counts.items()},
        "failure_count": failure_count, "failures": failures, "failures_omitted": failure_count - len(failures),
        "incomplete_events": None if format_name == "go-text" else 0,
        "unparsed_lines": None if format_name == "go-text" else 0, "acceptance_certified": False,
        "limits": ["Exit code describes the recorded process, not behavior conformance.",
                   "Skips and packages with no tests are not passes.",
                   "Counts describe observed terminal events; absent output is not a pass.",
                   "Text format cannot prove event completeness; failures need their full relevant diagnostics."],
    }
    result["needs_inspection"] = (exit_code != 0 or failure_count > 0 or not any(counts.values())
                                  or (counts["packages"].get("no_tests", 0) > 0
                                      and not counts["tests"] and not counts["packages"].get("pass", 0)))
    if exit_code not in (None, 0):
        result["failure_tail"] = list(tail)
        result["tail_is_bounded"] = True
    return result


def recorded_exit(args: argparse.Namespace) -> tuple[int | None, str | None]:
    if not args.receipt:
        return args.exit_code, None
    raw = args.receipt.read_bytes()
    receipt = json.loads(raw)
    if not isinstance(receipt, dict):
        raise AutomationError("receipt must be a JSON object")
    rows = receipt.get("steps", [receipt])
    if not isinstance(rows, list):
        raise AutomationError("receipt steps must be a list")
    matches = [row for row in rows if isinstance(row, dict) and isinstance(row.get("log"), str)
               and Path(row["log"]).resolve() == args.log.resolve()]
    if len(matches) != 1:
        raise AutomationError("receipt must contain exactly one matching log record")
    exit_code = matches[0].get("exit_code")
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        raise AutomationError("matching receipt has no recorded integer exit code")
    return exit_code, hashlib.sha256(raw).hexdigest()


def main() -> int:
    argv = sys.argv[1:]
    early_override = option_value(argv, "--error-log")
    early_log = early_override or option_value(argv, "--log")
    parser = ErrorLoggingArgumentParser(description=__doc__, error_log=Path(early_override) if early_override else default_error_log(early_log),
                                        context="summarize_check argparse")
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--format", choices=["go-json", "go-text"], required=True)
    evidence = parser.add_mutually_exclusive_group()
    evidence.add_argument("--exit-code", type=int, help="recorded process exit; omit if unavailable, never infer from log")
    evidence.add_argument("--receipt", type=Path, help="existing runner receipt or gates JSON with an exact matching log/exit")
    parser.add_argument("--error-log", type=Path)
    args = parser.parse_args(argv)
    error_log = args.error_log or default_error_log(args.log)
    try:
        exit_code, receipt_hash = recorded_exit(args)
        result = summarize(args.log, args.format, exit_code)
        if receipt_hash:
            result["exit_evidence"] = {"receipt": str(args.receipt.resolve()), "sha256": receipt_hash}
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except Exception as exc:
        report_error(exc, error_log, context="summarize_check")
        print(json.dumps({"schema_version": 2, "status": "analyzer_failed", "error": str(exc)}, ensure_ascii=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
