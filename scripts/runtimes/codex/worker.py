#!/usr/bin/env python3
# sliceworks 0.8.1. Host supervisor: persist thread.started immediately and service gate files without a model.
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from verification_source import atomic_json, candidate_host_file, candidate_launch_identity


def main():
    aid, registry, *command = sys.argv[1:]
    reg = Path(registry)
    isolated_candidate = os.environ.pop("SW_ISOLATED_CANDIDATE_ALLOC", "")
    if isolated_candidate:
        root = Path(os.environ["CLAUDE_PROJECT_DIR"]).resolve()
        allocation = json.loads(Path(isolated_candidate).read_text())
        if allocation["id"] != aid:
            raise ValueError("isolated launch allocation mismatch")
        launch_record = candidate_host_file(root, aid, "launch.json")
        launch_identity = candidate_launch_identity(Path.cwd(), allocation)

    child = subprocess.Popen(command, stdout=subprocess.PIPE, bufsize=0)
    if isolated_candidate:
        try:
            launch_record.parent.mkdir(parents=True, exist_ok=True)
            atomic_json(launch_record, launch_identity)
        except OSError:
            child.terminate()
            child.wait()
            raise

    def stream():
        for line in child.stdout:
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()
            try:
                event = json.loads(line)
                if isinstance(event, dict) and event.get('type') == 'thread.started':
                    thread = event['thread_id']
                    if not isinstance(thread, str) or not thread or '\n' in thread:
                        continue
                    tmp = reg / (aid + '.thread.tmp')
                    tmp.write_text(thread + '\n')
                    tmp.replace(reg / (aid + '.thread'))
            except (ValueError, KeyError):
                pass
    reader = threading.Thread(target=stream)
    reader.start()
    runner = None
    request = reg / aid / 'gate-request.json'
    env = dict(os.environ)
    env.pop('SW_ROLE', None)  # This supervisor is on the host, outside the writer's sandbox.
    while child.poll() is None:
        if (runner is None or runner.poll() is not None) and request.exists():
            runner = subprocess.Popen(['sh', str(Path(__file__).with_name('gate-runner.sh')), aid],
                                      env=env, stdout=sys.stderr, stderr=sys.stderr)
        time.sleep(.1)
    reader.join()
    if runner is not None:
        runner.wait()
    # A writer may return HOLD immediately after its atomic request rename.
    # Drain that final request even if it arrived between the last poll and CLI exit.
    if request.exists():
        subprocess.run(['sh', str(Path(__file__).with_name('gate-runner.sh')), aid],
                       env=env, stdout=sys.stderr, stderr=sys.stderr)
    return child.returncode


if __name__ == '__main__':
    raise SystemExit(main())
