#!/usr/bin/env python3
# sliceworks 0.8.2. The collector (method chapter 19): completion read from durable artifacts, never from a message.
#   collect.py --root <repo> [--state-dir docs/process] [--json]
# For every open or stopped allocation prints one line:
#   ALLOC <id> <STATE> <detail>
# States: RUNNING (a recorded pid is alive, or the latest tier log has no RESULT= yet), QUEUED (the queue marker exists:
# a legitimate wait for a shared resource), DONE (handoff present, its head equals the branch head, and the verification
# it names matches the gate receipt or tier evidence), BLOCKED or
# HOLD (from the handoff), STALE-HANDOFF (branch moved past the handoff head), CANDIDATE-UNVERIFIED (handoff claims a
# candidate but the evidence does not prove it), STOPPED-NO-HANDOFF (nothing runs and nothing was written),
# MISSING-WORKTREE. After the allocations it prints UNREGISTERED lines for worktrees, pid files and result-less logs
# that no open allocation owns, so an empty registry is never a clean report.
# Detection is read-only by default. --merge-worker-metrics imports staged rows as the coordinator; no message is sent.
import argparse, json, os, pathlib, re, subprocess, sys
import fcntl
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from safe_git import git_command
from survey import read_config
from verification_source import (FULL_SHA, accepted_base, candidate_command, candidate_gate_record,
                                 candidate_policy, gate_artifacts_match, last_result, require_ancestor,
                                 require_candidate_launch, require_sealed_checkout, uses_candidate_cadence)


def git(cwd, *args):
    r = subprocess.run(git_command("-C", cwd, *args), capture_output=True, text=True, check=False)
    return r.stdout.strip() if r.returncode == 0 else None


def pid_alive(path):
    try:
        pid = int(pathlib.Path(path).read_text().strip())
    except Exception:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def parse_handoff(text):
    if not text.startswith("---\n") or "\n---\n" not in text:
        return {}
    fm = text.split("\n---\n", 1)[0]
    out = {}
    for line in fm.splitlines():
        m = re.match(r"^(\w+):\s*(.*)$", line.strip())
        if m:
            out[m.group(1)] = m.group(2).strip()
    v = out.get("verification", "")
    m = re.search(r"result:\s*(pass|fail|NOT_RUN)", v)
    out["verification_result"] = m.group(1) if m else None
    m = re.search(r"log:\s*(.+?)(?:,\s*\w+:|}$|$)", v)
    out["verification_log"] = m.group(1).strip() if m else None
    return out


def latest_log_result(root, log_dir):
    if not log_dir:
        return None, None
    d = root / log_dir
    if not d.is_dir():
        return None, None
    logs = sorted(d.glob("t*-*.log"), key=lambda p: p.stat().st_mtime)
    if not logs:
        return None, None
    text = logs[-1].read_text(errors="ignore")
    m = re.findall(r"^RESULT=(\w+)", text, re.M)
    return str(logs[-1].relative_to(root)), (m[-1] if m else None)


def verification_proven(root, state_dir, h, alloc, wt, run_dir, policy=None):
    """Match the handoff to the specific execution, with legacy tier-log support."""
    head = h.get("head")
    if not head or not FULL_SHA.fullmatch(head) or h.get("base") != alloc["base"]:
        return False, "handoff must name the checked full head and assigned base"
    if h.get("verification_result") != "pass":
        return False, f"handoff verification {h.get('verification_result') or 'missing'}"
    log = h.get("verification_log")
    if not log:
        return False, "handoff names no log"
    lp = (root / log).absolute()
    if policy and (lp.is_symlink() or not lp.resolve().is_relative_to(root)):
        return False, "candidate log must be inside the project"
    if not lp.is_file():
        return False, f"log {log} not found"
    marker = last_result(lp)
    if marker != "pass":
        return False, f"log {log} ends with RESULT={marker or 'none'}"

    artifacts = root / run_dir / "codex" / alloc["id"]
    request_id = h.get("gate_request")
    # Recognize broker logs even if a handoff omits the new request field.
    if lp.resolve().parent == artifacts.resolve():
        match = re.fullmatch(r"gate-([A-Za-z0-9_-]{1,80})\.log", lp.name)
        if match:
            request_id = request_id or match[1]
    if policy and request_id is None:
        return False, "candidate cadence requires a named host gate"
    if request_id is not None:
        expected = {"request_id": request_id, "head": head, "base": alloc["base"],
                    "allocation": alloc["id"], "slice": alloc["slice"], "worktree": str(wt.resolve()),
                    "tier": "t1", "result": "pass", "exit_code": 0, "delivery": "fresh", "log": str(lp)}
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", request_id):
            return False, "invalid gate request id"
        try:
            path = artifacts / f"gate-{request_id}.json"
            if path.is_symlink() or artifacts.resolve() != artifacts:
                raise ValueError("symlink gate artifacts")
            receipt = json.loads(path.read_text())
            expected["accepted_base"] = accepted_base(alloc)
            if policy:
                expected.update(inputs=policy[1], command=candidate_command(policy[0], wt, alloc))
                latest = json.loads(candidate_gate_record(root, expected).read_text())
                if latest != receipt:
                    raise ValueError("receipt differs from the latest actual host gate for this candidate")
            if (not isinstance(receipt, dict)
                    or type(receipt.get("exit_code")) is not int
                    or any(receipt.get(key) != value for key, value in expected.items())
                    or not gate_artifacts_match(receipt, artifacts, request_id)):
                raise ValueError("receipt identity, outcome or artifact digest differs")
        except (OSError, ValueError) as exc:
            return False, f"gate receipt {request_id}: {exc}"
        return True, f"{log} RESULT=pass (gate receipt {request_id})"

    tiers = root / state_dir / "metrics" / "tiers.jsonl"
    scoped = "accepted_base" in alloc
    if tiers.exists():
        try:
            rows = [json.loads(line) for line in tiers.read_text().splitlines() if line.strip()]
            if any(not isinstance(row, dict) for row in rows):
                raise ValueError("expected JSON objects")
        except (OSError, ValueError) as exc:
            return False, f"cannot read tiers evidence: {exc}"
        matching = []
        for row in rows:
            row_log = row.get("log")
            same_log = isinstance(row_log, str) and (root / row_log).resolve() == lp.resolve()
            row_head = row.get("head_full", row.get("head"))
            if same_log or row_head in (head, head[:8]):
                matching.append((row, same_log))
        if scoped:
            latest = next((row for row, same_log in reversed(matching) if same_log), {})
            expected = {"head_full": head, "base": alloc["base"], "accepted_base": accepted_base(alloc),
                        "slice": alloc["slice"], "allocation": alloc["id"], "worktree": str(wt.resolve()),
                        "tier": "t1", "result": "pass", "exit_code": 0}
            if (type(latest.get("exit_code")) is not int
                    or any(latest.get(key) != value for key, value in expected.items())):
                return False, "latest row for the named log does not prove this allocation, checkout and source"
            return True, f"{log} RESULT=pass (matching tier row)"
        named = any(same_log for _, same_log in matching)
        legacy = [row for row, same_log in matching if (same_log if named else not row.get("log"))
                  and row.get("head_full", row.get("head")) in (head, head[:8])
                  and row.get("base", alloc["base"]) == alloc["base"]
                  and row.get("slice", alloc["slice"]) == alloc["slice"] and row.get("tier") == "t1"]
        if not legacy or legacy[-1].get("result") != "pass" or legacy[-1].get("exit_code", 0) != 0:
            return False, f"no passing legacy T1 row for head {head[:8]}"
    elif scoped:
        return False, "no tier execution rows for the scoped allocation"
    return True, f"{log} RESULT=pass (legacy evidence)"


def unregistered(root, state_dir, allocs, worktree_root, outputs_dir):
    """Evidence of work that no open allocation owns: linked worktrees (from git itself), live pid files, result-less logs."""
    owned_wt = {str((root / a["worktree"]).resolve()) if not pathlib.Path(a["worktree"]).is_absolute() else str(pathlib.Path(a["worktree"]).resolve()) for a in allocs}
    owned_pid = {(a.get("execution") or {}).get("pid_file") for a in allocs}
    owned_logs = {(a.get("execution") or {}).get("log_dir") for a in allocs}
    out = []
    main_wt = str(root.resolve())
    porcelain = git(root, "worktree", "list", "--porcelain") or ""
    for block in porcelain.split("\n\n"):
        lines = block.strip().splitlines()
        if not lines or not lines[0].startswith("worktree "):
            continue
        path = lines[0][len("worktree "):].strip()
        try:
            rp = str(pathlib.Path(path).resolve())
        except Exception:
            rp = path
        if rp == main_wt or rp in owned_wt:
            continue
        branch = next((l[len("branch refs/heads/"):] for l in lines if l.startswith("branch refs/heads/")), "detached")
        try:
            shown = str(pathlib.Path(rp).relative_to(root.resolve()))
        except ValueError:
            shown = rp
        out.append(("worktree", shown, branch))
    run = root / ".run"
    if run.is_dir():
        for pf in sorted(run.glob("*.pid")):
            rel = str(pf.relative_to(root))
            if rel not in owned_pid and pid_alive(pf):
                out.append(("pid", rel, "alive"))
    od = root / outputs_dir / "slices"
    if od.is_dir():
        for sd in sorted(p for p in od.iterdir() if p.is_dir()):
            rel = str(sd.relative_to(root))
            if rel in owned_logs:
                continue
            log, result = latest_log_result(root, rel)
            if log and result is None:
                out.append(("log", log, "no RESULT= yet"))
    return out


def candidate_identity(root, wt, alloc):
    return (wt.resolve() != root and git(wt, "rev-parse", "--show-toplevel") == str(wt.resolve())
            and git(wt, "rev-parse", "--path-format=absolute", "--git-common-dir") == str(root / ".git")
            and isinstance(alloc.get("branch"), str)
            and git(wt, "symbolic-ref", "--short", "HEAD") == alloc["branch"])


def candidate_handoff(root, state_dir, alloc, wt, run_dir):
    """Assess an opt-in handoff without declaring a live worker finished."""
    if not candidate_identity(root, wt, alloc):
        return "CANDIDATE-UNVERIFIED", "worktree or branch differs from the allocation"
    marker = wt / ".blocked"
    if marker.exists():
        with marker.open(errors="replace") as stream:
            if stream.readline().startswith("BLOCKED"):
                return "BLOCKED", "worker recorded BLOCKED"
        return "HOLD", "worker recorded HOLD"

    relative = f"{state_dir}/handoffs/{alloc['id']}.md"
    handoff = wt / relative
    if not handoff.exists():
        return "STOPPED-NO-HANDOFF", f"no {relative}; allocation may continue"
    text = handoff.read_text(errors="replace")
    h = parse_handoff(text)
    state = h.get("result")
    if state in ("HOLD", "BLOCKED"):
        return state, f"handoff {relative}"
    head = git(wt, "rev-parse", "HEAD")
    if not head or h.get("allocation") != alloc["id"] or state != "CANDIDATE" or not h.get("head"):
        return "CANDIDATE-UNVERIFIED", "missing or mismatched candidate handoff"
    if git(wt, "show", head + ":" + relative) != text.strip():
        return "CANDIDATE-UNVERIFIED", "candidate handoff differs from the committed checkout"
    source = h["head"]
    if source != head and not (
        git(wt, "rev-parse", "HEAD^") == source
        and git(wt, "diff", "--name-only", "-z", "--no-renames", source, head, "--") == relative + "\0"
    ):
        return "STALE-HANDOFF", "candidate handoff does not describe the checkout head"
    try:
        require_sealed_checkout(wt, head)
    except (OSError, ValueError, subprocess.CalledProcessError):
        return "STALE-HANDOFF", "checkout has moved or contains further work"
    try:
        require_ancestor(wt, alloc["base"], source)
        require_ancestor(wt, accepted_base(alloc), alloc["base"])
        policy = candidate_policy(root)
        if not policy:
            raise ValueError("candidate policy not configured")
        proven, why = verification_proven(root, state_dir, h, alloc, wt, run_dir, policy)
    except (KeyError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        return "CANDIDATE-UNVERIFIED", str(exc)
    return ("DONE" if proven else "CANDIDATE-UNVERIFIED"), f"candidate at {source}, {why}"


def candidate_allocations(root, state_dir, wt, cfg):
    for path in (root / state_dir / "allocations").glob("*.json"):
        alloc = json.loads(path.read_text())
        if not isinstance(alloc, dict):
            raise ValueError(f"invalid allocation: {path.name}")
        if (alloc.get("id") != path.stem or alloc.get("state") not in ("open", "stopped")
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", path.stem)
                or not uses_candidate_cadence(alloc, cfg)):
            continue
        if (root / alloc["worktree"]).resolve() == wt and candidate_identity(root, wt, alloc):
            yield alloc


def candidate_stop(root, state_dir, wt, run_dir, allocation_id):
    cfg = read_config(root) or {}
    if cfg.get("SW_VERIFY_CADENCE") != "candidate":
        return "LEGACY"
    try:
        matches = list(candidate_allocations(root, state_dir, wt, cfg))
        if len(matches) != 1:
            return "LEGACY"
        if matches[0].get("state") != "open" or matches[0]["id"] != allocation_id:
            return "LEGACY"
        require_candidate_launch(root, wt, matches[0])
        state, _ = candidate_handoff(root, state_dir, matches[0], wt, run_dir)
        if state in ("STOPPED-NO-HANDOFF", "STALE-HANDOFF"):
            candidate_policy(root)
        return state
    except (OSError, ValueError, KeyError, TypeError):
        return "LEGACY"


def assess(root, state_dir, alloc, run_dir=".run", candidate_config=None):
    wt = pathlib.Path(alloc["worktree"])
    wt = wt if wt.is_absolute() else root / wt
    if not wt.exists():
        return "MISSING-WORKTREE", f"{alloc['worktree']} does not exist"
    pid_file = (alloc.get("execution") or {}).get("pid_file")
    if pid_file and pid_alive(root / pid_file):
        return "RUNNING", f"pid in {pid_file} is alive"
    qm = (alloc.get("execution") or {}).get("queue_marker")
    if qm and (root / qm).exists():
        return "QUEUED", f"queue marker {qm} present: waiting for a shared resource"
    log_dir = (alloc.get("execution") or {}).get("log_dir")
    log, result = latest_log_result(root, log_dir)
    if log and result is None:
        return "RUNNING", f"{log} has no RESULT= yet"
    if candidate_config is not None:
        try:
            ids = [item["id"] for item in candidate_allocations(root, state_dir, wt.resolve(), candidate_config)]
            if ids != [alloc["id"]]:
                return "CANDIDATE-UNVERIFIED", "candidate requires one matching registered allocation"
            require_candidate_launch(root, wt, alloc)
            gate_dir = root / run_dir / "codex" / alloc["id"]
            if any((gate_dir / name).exists() for name in ("gate-request.json", "gate-active.json", "gate.lock")):
                return "QUEUED", "host gate request awaits completion or reconciliation"
            return candidate_handoff(root, state_dir, alloc, wt, run_dir)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return "CANDIDATE-UNVERIFIED", str(exc)
    head = git(wt, "rev-parse", "HEAD")
    handoff_rel = f"{state_dir}/handoffs/{alloc['id']}.md"
    handoff_path = wt / handoff_rel
    if not handoff_path.exists():
        handoff_path = root / handoff_rel
    if not handoff_path.exists():
        return "STOPPED-NO-HANDOFF", f"no process, no {handoff_rel}; branch head {head[:8] if head else '?'}"
    handoff_text = handoff_path.read_text(errors="ignore")
    h = parse_handoff(handoff_text)
    if h.get("gate_request") and handoff_path == wt / handoff_rel:
        if not head or git(wt, "show", head + ":" + handoff_rel) != handoff_text.strip():
            return "CANDIDATE-UNVERIFIED", "brokered handoff is missing at the checkout head or changed on disk"
    if h.get("head") and head and h["head"] != head:
        # Allow a final commit that publishes only this allocation's handoff.
        # Read it at that commit so uncommitted edits cannot change the claim.
        publishes_handoff = (h.get("gate_request") and handoff_path == wt / handoff_rel
                             and git(wt, "rev-parse", "HEAD^") == h["head"]
                             and git(wt, "diff", "--name-only", "-z", "--no-renames",
                                     h["head"], head, "--") == handoff_rel + "\0")
        if not publishes_handoff:
            return "STALE-HANDOFF", f"handoff head {h['head'][:8]} but branch head {head[:8]}"
    res = (h.get("result") or "").upper()
    if res in ("BLOCKED", "HOLD"):
        return res, f"handoff {handoff_rel}: {h.get('verification_result') or 'no verification'}"
    if res == "CANDIDATE":
        if not head or h.get("allocation") != alloc["id"]:
            return "CANDIDATE-UNVERIFIED", "missing checkout head or mismatched handoff allocation"
        ok, why = verification_proven(root, state_dir, h, alloc, wt, run_dir)
        if ok:
            return "DONE", f"candidate at {head[:8]}, {why}"
        return "CANDIDATE-UNVERIFIED", f"candidate at {head[:8]}: {why}"
    return "STOPPED-NO-HANDOFF", f"handoff present but result unreadable: {res or 'none'}"


def reported_gate(root, run_dir, allocation_id):
    """Expose the runner's latest report even before a handoff is available."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", allocation_id):
        return None
    path = root / run_dir / "codex" / allocation_id / "gate-result.json"
    if not path.exists():
        return None
    try:
        if path.resolve() != path:
            raise ValueError("symlink gate report")
        result = json.loads(path.read_text())
        if not isinstance(result, dict) or result.get("result") not in ("pass", "fail", "NOT_RUN"):
            raise ValueError("invalid gate report")
        return {key: result.get(key) for key in ("request_id", "head", "base", "accepted_base",
                "result", "exit_code", "delivery", "log", "error")}
    except (OSError, ValueError) as exc:
        return {"result": "UNREADABLE", "error": str(exc)}


def merge_worker_metrics(root, state_dir, run_dir):
    """Coordinator-only opt-in import; preserve rows and make repeated collection idempotent."""
    target = root / state_dir / "metrics"
    target.mkdir(parents=True, exist_ok=True)
    merged = 0
    # Serialize coordinator imports so two collectors never duplicate a row.
    with (target / ".worker-merge.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for source in sorted((root / run_dir / "codex").glob("*/metrics/*.jsonl")):
            if source.is_symlink() or not re.fullmatch(r"[a-z][a-z0-9_-]*\.jsonl", source.name):
                raise ValueError(f"invalid worker metrics path: {source}")
            raw = source.read_text()
            # A running writer may be between writes; consume complete lines only.
            lines = raw.splitlines() if raw.endswith("\n") else raw.splitlines()[:-1]
            rows = [json.loads(line) for line in lines if line.strip()]
            if any(not isinstance(row, dict) for row in rows):
                raise ValueError(f"worker metrics must contain objects: {source}")
            dest = target / source.name
            if dest.is_symlink():
                raise ValueError(f"symlink metrics destination: {dest}")
            existing = {json.dumps(json.loads(line), sort_keys=True) for line in dest.read_text().splitlines() if line.strip()} if dest.exists() else set()
            with dest.open("a") as out:
                for row in rows:
                    key = json.dumps(row, sort_keys=True)
                    if key not in existing:
                        out.write(json.dumps(row) + "\n")
                        existing.add(key)
                        merged += 1
    return merged


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--state-dir", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--candidate-stop", type=pathlib.Path, metavar="WORKTREE")
    ap.add_argument("--allocation", default="", help="trusted launcher allocation for --candidate-stop")
    ap.add_argument("--merge-worker-metrics", action="store_true", help="coordinator: import staged worker rows before assessing allocations")
    a = ap.parse_args(argv)
    root = pathlib.Path(a.root).resolve()
    state_dir = a.state_dir
    if state_dir is None:
        state_dir = "docs/process"
        cfg = root / ".sliceworks" / "config.env"
        if cfg.exists():
            m = re.search(r"^SW_STATE_DIR=(\S+)", cfg.read_text(), re.M)
            if m:
                state_dir = m.group(1).strip('"')
    worktree_root, outputs_dir, run_dir = ".claude/worktrees", "outputs", ".run"
    cfg = root / ".sliceworks" / "config.env"
    if cfg.exists():
        t = cfg.read_text()
        m = re.search(r"^SW_WORKTREE_ROOT=(\S+)", t, re.M); worktree_root = m.group(1).strip('"') if m else worktree_root
        m = re.search(r"^SW_OUTPUTS_DIR=(\S+)", t, re.M); outputs_dir = m.group(1).strip('"') if m else outputs_dir
        m = re.search(r"^SW_RUN_DIR=(\S+)", t, re.M); run_dir = m.group(1).strip('"') if m else run_dir
    if a.candidate_stop is not None:
        print(candidate_stop(root, state_dir, a.candidate_stop.resolve(), run_dir, a.allocation))
        return 0
    if a.merge_worker_metrics:
        if os.environ.get("SW_ROLE"):
            raise SystemExit("collect: only the coordinator merges worker metrics")
        merge_worker_metrics(root, state_dir, run_dir)
    adir = root / state_dir / "allocations"
    rows = []; open_allocs = []
    config = read_config(root) or {}
    for f in sorted(adir.glob("*.json")) if adir.is_dir() else []:
        try:
            alloc = json.loads(f.read_text())
        except Exception as e:
            rows.append({"id": f.stem, "state": "UNREADABLE", "detail": str(e)}); continue
        if alloc.get("state") in ("closed", "collected"):
            continue
        open_allocs.append(alloc)
        candidate = uses_candidate_cadence(alloc, config)
        state, detail = assess(root, state_dir, alloc, run_dir, config if candidate else None)
        w = alloc.get("worker") or {}; ex = alloc.get("execution") or {}
        rows.append({"id": alloc["id"], "slice": alloc.get("slice"), "role": alloc.get("role"), "state": state, "detail": detail,
                     "chat": w.get("chat_id"), "session": ex.get("session_id") or w.get("id")})
        if candidate:
            rows[-1]["cadence"] = "candidate"
        gate = reported_gate(root, run_dir, alloc["id"])
        if gate:
            rows[-1]["gate"] = gate
    extra = unregistered(root, state_dir, open_allocs, worktree_root, outputs_dir)
    if a.json:
        print(json.dumps({"allocations": rows, "unregistered": [{"kind": k, "path": p, "detail": x} for k, p, x in extra]}, indent=2))
    else:
        for r in rows:
            ids = " ".join(f"{k}={v}" for k, v in (("chat", r.get("chat")), ("session", r.get("session"))) if v)
            cadence = " [candidate cadence]" if r.get("cadence") == "candidate" else ""
            print(f"ALLOC {r['id']} {r['state']} {r['detail']}{cadence}{(' [' + ids + ']') if ids else ''}")
            if gate := r.get("gate"):
                print(f"GATE {r['id']} {gate.get('request_id') or '-'} {gate['result']} "
                      f"{gate.get('head') or '-'} {gate.get('log') or gate.get('error') or '-'}")
        if not rows:
            print("ALLOC none open")
        for k, p, x in extra:
            print(f"UNREGISTERED {k} {p} {x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
