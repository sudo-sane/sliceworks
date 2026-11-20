#!/usr/bin/env python3
"""Run one authorized check with a complete new log and a bounded JSON receipt."""

from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
import subprocess
import sys
import time

from automation_errors import (AutomationError, ErrorLoggingArgumentParser,
                               default_error_log, option_value, report_error)


def positive_count(value):
    count = int(value)
    if count <= 0:
        raise argparse.ArgumentTypeError("expected a positive count")
    return count


def run(args: argparse.Namespace) -> int:
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise AutomationError("a command is required after --")
    cwd = args.cwd.resolve()
    log = args.log.absolute()  # Relative to the caller, never the child cwd.
    error_log = args.error_log or default_error_log(log)
    if not cwd.is_dir():
        error = ValueError("--cwd must be an existing directory")
        report_error(error, error_log, context="run_logged_check")
        print(json.dumps({"status": "not_run", "error": str(error), "log": str(log)}))
        return 2
    try:
        if log.is_symlink():
            raise OSError("refusing symbolic-link log: " + str(log))
        stream = log.open("xb")
    except Exception as exc:
        report_error(exc, error_log, context="run_logged_check")
        print(json.dumps({"status": "not_run", "error": str(exc), "log": str(log)}))
        return 2
    started = time.monotonic()
    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    launch_error = None
    interrupted = False
    with stream:
        try:
            child = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL,
                                     stdout=stream, stderr=subprocess.STDOUT)
        except Exception as exc:
            launch_error = exc
            stream.write((str(exc) + "\n").encode())
            raw_exit = None
        else:
            try:
                raw_exit = child.wait()
            except KeyboardInterrupt:
                interrupted = True
                child.terminate()
                try:
                    raw_exit = child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    raw_exit = child.wait()
    if raw_exit is None:
        exit_code = 127
    else:
        exit_code = 130 if interrupted else (raw_exit if raw_exit >= 0 else 128 - raw_exit)
    size = log.stat().st_size
    result = {"status": "not_run" if launch_error else ("interrupted" if interrupted else
              "passed" if exit_code == 0 else "failed"), "exit_code": exit_code,
              "raw_exit_code": raw_exit, "elapsed_seconds": round(time.monotonic() - started, 3),
              "log": str(log), "log_bytes": size, "cwd": str(cwd),
              "started_at": None if launch_error else started_at,
              "at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    analyzer_failed = False
    selection_failed = False
    if args.expect_passed is not None:
        result["expected_passed_tests"] = args.expect_passed
    if launch_error:
        report_error(launch_error, error_log, context="run_logged_check launch")
    elif exit_code:
        report_error(AutomationError("child check exited " + str(exit_code) + "; full raw log: " + str(log)),
                     error_log, context="run_logged_check child")
    if args.summary and not launch_error:
        try:
            from summarize_check import summarize
            result["observed_checks"] = summarize(log, args.summary, exit_code)
        except Exception as exc:
            analyzer_failed = True
            result["status"] = "analyzer_failed"
            result["analyzer_error"] = str(exc)
            report_error(exc, error_log, context="run_logged_check analyzer")
    if args.expect_passed is not None and "observed_checks" in result:
        observed = result["observed_checks"]
        counts = observed["counts"]
        passed = counts["tests"].get("pass", 0)
        skipped = sum(counts[kind].get("skip", 0) for kind in ("tests", "subtests"))
        selection_failed = passed != args.expect_passed or skipped > 0 or observed["failure_count"] > 0
        if selection_failed:
            error = (f"expected {args.expect_passed} passing tests, observed {passed}, "
                     f"{skipped} test skips and {observed['failure_count']} failing events")
            result["selection_error"] = error
            if exit_code == 0:
                result["status"] = "selection_failed"
            report_error(AutomationError(error), error_log, context="run_logged_check selection")
    if exit_code and "observed_checks" not in result:
        try:
            with log.open("rb") as source:
                source.seek(max(0, size - 8192))
                tail = source.read().decode("utf-8", errors="replace").splitlines()
            result["failure_tail"] = "\n".join(tail[-30:])
            result["tail_may_be_incomplete"] = size > 8192 or len(tail) > 30
        except Exception as exc:
            analyzer_failed = True
            result["status"] = "analyzer_failed"
            result["analyzer_error"] = str(exc)
            report_error(exc, error_log, context="run_logged_check receipt")
    try:
        print(json.dumps(result, ensure_ascii=True))
    except Exception as exc:
        report_error(exc, error_log, context="run_logged_check receipt output")
        return exit_code if exit_code else 2
    # Preserve a child's nonzero result.  A child success with a bad analyzer is
    # an automation failure and must never be reported as success.
    return exit_code if exit_code else (2 if analyzer_failed or selection_failed else 0)


def main() -> int:
    argv = sys.argv[1:]
    early_override = option_value(argv, "--error-log")
    early_log = early_override or option_value(argv, "--log")
    parser = ErrorLoggingArgumentParser(description=__doc__, error_log=Path(early_override) if early_override else default_error_log(early_log),
                                        context="run_logged_check argparse")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--summary", choices=["go-json", "go-text"],
                        help="add bounded observed test counts; full log and exit remain authoritative")
    parser.add_argument("--expect-passed", type=positive_count, metavar="N",
                        help="require exactly N passing top-level tests, with no failed events or test skips")
    parser.add_argument("--error-log", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")
    if args.expect_passed is not None and args.summary != "go-json":
        parser.error("--expect-passed requires --summary go-json")
    try:
        return run(args)
    except Exception as exc:
        error_log = args.error_log or default_error_log(args.log)
        report_error(exc, error_log, context="run_logged_check runtime")
        try:
            print(json.dumps({"status": "automation_failed", "error": str(exc), "log": str(args.log.absolute())}))
        except Exception as output_exc:
            report_error(output_exc, error_log, context="run_logged_check runtime output")
        return 2


if __name__ == "__main__":
    sys.exit(main())
