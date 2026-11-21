#!/usr/bin/env python3
# sliceworks 0.8.2. Request data selects an allocation and T1, never a shell command.
"""Run one pending gate request through the project's trusted, slot-admitting verifier."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time
import uuid
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from safe_git import git_command
from verification_source import (accepted_base, candidate_command, candidate_gate_record, candidate_policy,
                                 coverage_path, cumulative_changes, file_digest, gate_artifacts_match,
                                 last_result, require_ancestor, require_sealed_checkout)


def atomic_json(path, value):
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    tmp.write_text(json.dumps(value) + '\n')
    tmp.replace(path)


def git(path, *args):
    return subprocess.check_output(git_command('-C', path, *args), text=True).strip()


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def run(aid):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', aid):
        raise ValueError('invalid allocation id')
    root = Path(os.environ['SW_ROOT']).resolve()
    run_dir = root / os.environ['SW_RUN_DIR'] / 'codex' / aid
    if run_dir.resolve() != run_dir or not run_dir.is_relative_to(root):
        raise ValueError('gate run directory must be inside the project without symlinks')
    request = run_dir / 'gate-request.json'
    if not request.exists():
        return 0
    lock = run_dir / 'gate.lock'
    try:
        lock.mkdir()
    except FileExistsError:
        return 0  # A single runner owns this request and its artifacts.

    result = {'result': 'NOT_RUN', 'exit_code': None, 'log': None}
    active = run_dir / 'gate-active.json'
    owned_active = False
    owned_log = False
    authoritative = None
    try:
        if request.is_symlink() or active.exists() or active.is_symlink():
            raise ValueError('symlink request or unresolved active gate; inspect before retrying')
        request.rename(active)
        owned_active = True
        req = json.loads(active.read_text())
        if not isinstance(req, dict):
            raise ValueError('request must be an object')
        result.update(request_id=req.get('request_id'), head=req.get('head'))
        if set(req) != {'request_id', 'allocation', 'slice', 'head', 'tier'}:
            raise ValueError('request must contain only request_id, allocation, slice, head, tier')
        rid = req['request_id']
        if (not isinstance(rid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', rid)
                or rid.lower() in ('active', 'request', 'result')):
            raise ValueError('invalid request_id')
        receipt = run_dir / ('gate-' + rid + '.json')
        saved = None
        if receipt.exists() or receipt.is_symlink():
            if receipt.is_symlink():
                raise ValueError('symlink gate receipt')
            saved = json.loads(receipt.read_text())
            if not isinstance(saved, dict) or any(saved.get(key) != value for key, value in req.items()):
                raise ValueError('request_id was already used for different source or allocation')

        alloc = json.loads((root / os.environ['SW_STATE_DIR'] / 'allocations' / (aid + '.json')).read_text())
        if alloc.get('role', 'slice-implementer').split(':')[-1] != 'slice-implementer':
            raise ValueError('host gate requires an implementer allocation')
        if alloc.get('state', 'open') not in ('open', 'stopped'):
            raise ValueError('allocation is closed or has an invalid state')
        if alloc.get('mode', 'full') != 'full':
            raise ValueError('host gate requires a full allocation')
        if req['allocation'] != aid or req['slice'] != alloc['slice'] or req['tier'] != 't1':
            raise ValueError('allocation/slice mismatch or disallowed tier (only t1)')
        wt = (root / alloc['worktree']).resolve()
        if wt == root or Path(git(wt, 'rev-parse', '--show-toplevel')).resolve() != wt:
            raise ValueError('gate requires an assigned linked worktree')
        if Path(git(wt, 'rev-parse', '--path-format=absolute', '--git-common-dir')).resolve() != root / '.git':
            raise ValueError('worktree belongs to another repository')
        if alloc.get('branch') and git(wt, 'symbolic-ref', '--short', 'HEAD') != alloc['branch']:
            raise ValueError('worktree branch differs from allocation')
        base = alloc['base']
        accepted = accepted_base(alloc)
        binding = dict(base=base, accepted_base=accepted, worktree=str(wt))
        if saved is not None and any(saved.get(key) != value for key, value in binding.items()):
            raise ValueError('request_id was already used for a different base or checkout')
        result.update(**req, **binding)
        require_ancestor(wt, base, req['head'])
        require_ancestor(wt, accepted, base)
        require_sealed_checkout(wt, req['head'])
        if (root / os.environ['SW_STOP_FILE']).exists():
            raise ValueError('STOP kill switch present')
        policy = candidate_policy(root)
        if policy:
            if os.environ['SW_VERIFY_CADENCE'] != 'candidate' or not alloc.get('branch'):
                raise ValueError('candidate cadence requires matching launcher configuration and allocation branch')
            if os.environ['SW_PREHANDOFF_CMD'] != f"{os.environ['SW_VERIFY_CMD']} {os.environ['SW_T0_ARGS']}":
                raise ValueError('candidate cadence requires the complete configured T1 verifier')
            command = candidate_command(policy[0], wt, alloc)
            result.update(inputs=policy[1], command=command)
            host_record = candidate_gate_record(root, result)
            if saved is None:
                host_record.parent.mkdir(parents=True, exist_ok=True)
                atomic_json(host_record, {**result, "result": "NOT_RUN", "error": "host gate pending"})
                authoritative = host_record
            elif json.loads(host_record.read_text()) != saved:
                raise ValueError('saved gate is no longer the latest actual host gate for this candidate')
        elif os.environ['SW_VERIFY_CADENCE'] == 'candidate':
            raise ValueError('candidate cadence differs between the prepared launcher and project policy')
        if saved is not None:
            if not gate_artifacts_match(saved, run_dir, rid):
                raise ValueError('saved gate artifacts are incomplete or changed; use a new request_id')
            result = {**saved, 'delivery': 'replayed'}
            return 0 if result['result'] == 'pass' else 1

        verify = (root / os.environ['SW_VERIFY_CMD']).resolve()
        if not verify.is_relative_to(root) or not verify.is_file() or not os.access(verify, os.X_OK):
            raise ValueError('configured main-checkout verifier is unavailable')
        paths = coverage_path(run_dir, rid)
        changes = cumulative_changes(wt, accepted, req['head'])
        manifest = (json.dumps(changes) + '\n').encode()
        with paths.open('xb') as out:
            out.write(manifest)
        log = run_dir / ('gate-' + rid + '.log')
        command = candidate_command(str(verify), wt, alloc)
        if policy:
            if str(verify) != policy[0]:
                raise ValueError('candidate verifier differs from the project policy')
            result['inputs'] = policy[1]
        result.update(command=command, log=str(log), delivery='fresh',
                      coverage=str(paths), coverage_sha256=hashlib.sha256(manifest).hexdigest())
        # Slot admission and every check remain the project verifier's responsibility.
        metrics = run_dir / 'metrics'
        tiers = metrics / 'tiers.jsonl'
        if metrics.is_symlink() or tiers.is_symlink():
            raise ValueError('symlink gate metrics')
        metrics.mkdir(exist_ok=True)
        env = {**os.environ, 'SW_ALLOCATION': aid, 'SW_CODEX_RUN_DIR': str(run_dir),
               'SW_METRICS_DIR': str(metrics), 'SW_TIERS_FILE': str(tiers),
               'SW_CUMULATIVE_CHANGES': str(paths)}
        started = time.monotonic()
        with log.open('x') as out:
            owned_log = True
            result['started_at'] = now()
            child = subprocess.run(command, cwd=wt, env=env, stdin=subprocess.DEVNULL,
                                   stdout=out, stderr=subprocess.STDOUT)
            result.update(exit_code=child.returncode, at=now(), seconds=int(time.monotonic() - started))
        marker = last_result(log)
        if marker == 'NOT_RUN':
            result.update(result='NOT_RUN', error='project verifier reported NOT_RUN; see log')
        elif child.returncode == 0 and marker == 'pass':
            result['result'] = 'pass'
        else:
            result.update(result='fail', error=f'verifier exit {child.returncode}, RESULT={marker or "missing"}')
        try:
            require_sealed_checkout(wt, req['head'])
            if policy and candidate_policy(root) != policy:
                raise ValueError('candidate verification policy changed during the run')
            if paths.is_symlink() or paths.read_bytes() != manifest:
                raise ValueError('cumulative changes manifest changed')
        except (ValueError, OSError, subprocess.CalledProcessError) as exc:
            result.update(result='fail', error=f'post-verification source check: {exc}')

        with log.open('a') as out:
            out.write('\nRESULT=' + result['result'] + '\n')
        result['log_sha256'] = file_digest(log)
        # The project can write detailed step rows. This row records the broker's own process.
        row = {**result, 'head_full': req['head'], 'head': req['head'][:8],
               'command': shlex.join(command)}
        with tiers.open('a') as out:
            out.write(json.dumps(row) + '\n')
        atomic_json(receipt, result)
    except Exception as exc:
        result.update(result='NOT_RUN' if result['exit_code'] is None else 'fail', error=str(exc))
        if owned_log:
            with Path(result['log']).open('a') as out:
                out.write('\nRESULT=' + result['result'] + '\n')
    finally:
        try:
            if authoritative is not None:
                atomic_json(authoritative, result)
            atomic_json(run_dir / 'gate-result.json', result)
        finally:
            if owned_active and active.exists():
                active.replace(run_dir / 'gate-request.last.json')
            lock.rmdir()
    return 0 if result['result'] == 'pass' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('allocation')
    args = parser.parse_args()
    raise SystemExit(run(args.allocation))
