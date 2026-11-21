#!/usr/bin/env python3
# sliceworks 0.8.9. Read cumulative changes for a project's trusted verification code.
"""Describe the committed delta from an accepted base to a sealed candidate."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from safe_git import git_command
from survey import read_config


FULL_SHA = re.compile(r"[0-9a-f]{40}")
LOCAL_MARKERS = {b"?? .slice", b"?? .blocked", b"?? .prehandoff-unavailable.json"}


def accepted_base(allocation):
    if "accepted_base" in allocation:
        return allocation["accepted_base"]
    if allocation.get("base_kind", "integration") == "integration":
        return allocation["base"]
    raise ValueError("stacked and companion allocations need an explicit accepted_base")


def require_ancestor(cwd, base, head):
    if not all(isinstance(sha, str) and FULL_SHA.fullmatch(sha) for sha in (base, head)):
        raise ValueError("base and candidate must be full commit SHAs")
    try:
        for sha in (base, head):
            commit = subprocess.check_output(
                git_command("-C", cwd, "rev-parse", "--verify", sha + "^{commit}"), stderr=subprocess.PIPE
            )
            if commit.strip().decode() != sha:
                raise ValueError("base and candidate must identify commits directly")
        if subprocess.call(git_command("-C", cwd, "merge-base", "--is-ancestor", base, head),
                           stderr=subprocess.PIPE):
            raise ValueError("base is not an ancestor of candidate")
    except subprocess.CalledProcessError as exc:
        raise ValueError("base or candidate commit is unavailable") from exc


def require_sealed_checkout(cwd, head):
    # Inspect the entire worktree even when the caller is in a subdirectory.
    actual = subprocess.check_output(git_command("-C", cwd, "rev-parse", "HEAD")).strip().decode()
    if actual != head:
        raise ValueError("request head is stale")
    status = subprocess.check_output(git_command("-C", cwd, "--no-optional-locks", "status",
                                                 "--porcelain=v1", "-z", "--untracked-files=all",
                                                 "--ignore-submodules=none"))
    if any(entry not in LOCAL_MARKERS for entry in status.split(b"\0")[:-1]):
        raise ValueError("commit tracked changes and intended new files before verification")


def cumulative_changes(cwd, base, head):
    require_ancestor(cwd, base, head)
    raw = subprocess.check_output(git_command(
        "-C", cwd, "diff", "--name-status", "-z", "--find-renames", "--no-ext-diff",
        "--ignore-submodules=none", base, head, "--",
    ))
    fields = iter(raw.split(b"\0")[:-1])
    changes = []
    for status in fields:
        code = status.decode("ascii")
        path = os.fsdecode(next(fields))
        if code.startswith(("R", "C")):
            changes.append({"status": code, "old_path": path, "path": os.fsdecode(next(fields))})
        else:
            changes.append({"status": code, "path": path})
    return {"accepted_base": base, "head": head, "changes": changes}


def file_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def candidate_policy(root):
    """Resolve the one coordinator-configured verifier for this opt-in cadence."""
    cfg = read_config(root) or {}
    if cfg.get("SW_VERIFY_CADENCE") != "candidate":
        return None
    command = cfg.get("SW_VERIFY_CMD", "scripts/dev/verify-slice.sh")
    t0 = cfg.get("SW_T0_ARGS", "t0")
    if cfg.get("SW_PREHANDOFF_CMD", "") not in ("", f"{command} {t0}"):
        raise ValueError("candidate cadence requires moving the separate pre-handoff check into the configured T1")
    verify = (root / command).resolve()
    if not verify.is_relative_to(root) or not verify.is_file() or not os.access(verify, os.X_OK):
        raise ValueError("configured main-checkout verifier is unavailable")
    return str(verify), {
        "config_sha256": file_digest(root / ".sliceworks" / "config.env"),
        "verifier_sha256": file_digest(verify),
    }


def candidate_command(verifier, worktree, allocation):
    return [verifier, "--cwd", str(worktree.resolve()), "--slice", allocation["slice"],
            "--base", allocation["base"], "t1"]


def last_result(path):
    result = None
    with path.open(errors="replace") as stream:
        for line in stream:
            if line.startswith("RESULT="):
                result = line.removeprefix("RESULT=").strip()
    return result


def coverage_path(run_dir, request_id):
    return run_dir / ("gate-" + request_id + ".changes.json")


def gate_artifacts_match(receipt, run_dir, request_id):
    artifacts = {
        "log": run_dir / ("gate-" + request_id + ".log"),
        "coverage": coverage_path(run_dir, request_id),
    }
    return all(receipt.get(key) == str(path) and not path.is_symlink() and path.is_file()
               and receipt.get(key + "_sha256") == file_digest(path)
               for key, path in artifacts.items())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--accepted-base", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args()
    try:
        require_sealed_checkout(args.cwd, args.head)
        print(json.dumps(cumulative_changes(args.cwd, args.accepted_base, args.head)))
    except (ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(2, f"NOT_RUN: {exc}\n")


if __name__ == "__main__":
    main()
