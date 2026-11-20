"""Exercise the verifier, collector and selector against disposable Git worktrees."""

import json
import pathlib
import subprocess
import sys

import test_codex_runtime as runtime


PKG = runtime.PKG
AID = "alloc-slice-07-r1"


class BoundedVerification(runtime.Project):
    def setUp(self):
        super().setUp()
        self.base = runtime.git(self.wt, "rev-parse", "HEAD")
        self.run_dir = self.root / ".run/codex" / AID
        self.run_dir.mkdir(parents=True)
        self.verify = self.root / "scripts/dev/verify-slice.sh"
        self.verify.parent.mkdir(parents=True)
        self.verifier('echo RESULT=pass')
        self.set_allocation()

    def set_allocation(self, **changes):
        self.alloc(AID, {"role": "slice-implementer", "worktree": str(self.wt),
                         "branch": "slice/07", "base": self.base, "state": "open", **changes})

    def verifier(self, body):
        self.verify.write_text("#!/bin/sh\nset -eu\n" + body + "\n")
        self.verify.chmod(0o755)

    def commit(self):
        runtime.git(self.wt, "add", "-A")
        runtime.git(self.wt, "commit", "-qm", "checkpoint")
        return runtime.git(self.wt, "rev-parse", "HEAD")

    def request(self, head=None, rid="bounded", **changes):
        req = {"request_id": rid, "allocation": AID, "slice": "slice-07", "tier": "t1",
               "head": head or runtime.git(self.wt, "rev-parse", "HEAD"), **changes}
        (self.run_dir / "gate-request.json").write_text(json.dumps(req))
        out = subprocess.run(["sh", str(runtime.CODEX / "gate-runner.sh"), AID],
                             cwd=self.root, env=self.environment(), capture_output=True, text=True, timeout=20)
        return out, json.loads((self.run_dir / "gate-result.json").read_text())

    def collect(self, merge=False):
        command = [sys.executable, str(PKG / "scripts/collect.py"), "--root", str(self.root), "--json"]
        if merge:
            command.append("--merge-worker-metrics")
        return json.loads(subprocess.check_output(command, text=True))["allocations"]

    def handoff(self, result, commit=True):
        path = self.wt / "docs/process/handoffs" / (AID + ".md")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"""---
allocation: {AID}
result: CANDIDATE
head: {result['head']}
base: {result['base']}
gate_request: {result['request_id']}
verification: {{tier: t1, log: {result['log']}, result: pass}}
---
""")
        if commit:
            self.commit()

    def test_cumulative_paths_reach_project_verifier_and_follow_accepted_base(self):
        (self.wt / "delete me").write_text("delete")
        (self.wt / "rename me").write_text("rename")
        accepted = self.commit()
        (self.wt / "earlier change").write_text("earlier")
        (self.wt / "delete me").unlink()
        (self.wt / "rename me").rename(self.wt / "renamed file")
        stacked = self.commit()
        (self.wt / "owned\tpath").write_text("owned")
        head = self.commit()
        self.set_allocation(base=stacked, base_kind="stacked", accepted_base=accepted,
                            allowed_paths=["owned\tpath"])
        self.verifier('cat "$SW_CUMULATIVE_CHANGES"\necho RESULT=pass')
        out, result = self.request(head)
        self.assertEqual(out.returncode, 0, result)
        self.assertEqual(result["base"], stacked)
        self.assertEqual(result["accepted_base"], accepted)
        manifest = json.loads(pathlib.Path(result["log"]).read_text().splitlines()[0])
        self.assertEqual(manifest["head"], head)
        self.assertCountEqual(manifest["changes"], [
            {"status": "D", "path": "delete me"},
            {"status": "R100", "old_path": "rename me", "path": "renamed file"},
            {"status": "A", "path": "earlier change"},
            {"status": "A", "path": "owned\tpath"},
        ])
        self.set_allocation(base=stacked, base_kind="stacked", accepted_base=stacked)
        out, refused = self.request(head)
        self.assertNotEqual(out.returncode, 0, refused)
        self.assertIn("different base", refused["error"])
        out, next_run = self.request(head, rid="new-base")
        self.assertEqual(out.returncode, 0, next_run)
        new_manifest = json.loads(pathlib.Path(next_run["coverage"]).read_text())
        self.assertEqual(new_manifest["changes"], [{"status": "A", "path": "owned\tpath"}])

    def test_stack_requires_explicit_ancestral_base_and_request_cannot_set_it(self):
        for changes, error in [
            ({}, "explicit accepted_base"),
            ({"accepted_base": "f" * 40}, "unavailable"),
        ]:
            self.set_allocation(base_kind="stacked", **changes)
            out, result = self.request()
            self.assertNotEqual(out.returncode, 0)
            self.assertEqual(result["result"], "NOT_RUN")
            self.assertIn(error, result["error"])
        self.set_allocation()
        out, result = self.request(accepted_base=self.base)
        self.assertNotEqual(out.returncode, 0)
        self.assertEqual(result["result"], "NOT_RUN")

    def test_preparation_only_allocation_keeps_the_gate_deferred(self):
        self.set_allocation(mode="prepare-only")
        out, result = self.request()
        self.assertNotEqual(out.returncode, 0)
        self.assertEqual(result["result"], "NOT_RUN")
        self.assertIn("requires a full allocation", result["error"])

    def test_request_id_cannot_alias_control_files(self):
        for rid in ("active", "request", "result"):
            with self.subTest(request_id=rid):
                out, result = self.request(rid=rid)
                self.assertNotEqual(out.returncode, 0)
                self.assertEqual(result["error"], "invalid request_id")
                self.assertIsNone(result["exit_code"])

    def test_cli_accepts_local_markers_but_rejects_a_different_head(self):
        (self.wt / ".slice").write_text("slice-07\n")
        (self.wt / ".blocked").write_text("HOLD\n")
        out, result = self.request()
        self.assertEqual(out.returncode, 0, result)
        prefix = [sys.executable, str(PKG / "scripts/verification_source.py"),
                  "--cwd", str(self.wt), "--accepted-base", self.base, "--head"]
        report = json.loads(subprocess.check_output([*prefix, self.base], text=True))
        self.assertEqual(report, {"head": self.base, "accepted_base": self.base, "changes": []})
        out = subprocess.run([*prefix, "0" * 40], capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)
        self.assertIn("NOT_RUN", out.stderr)

    def test_unsealed_input_refused_before_launch_and_mutation_preserves_actual_exit(self):
        source = self.wt / "unsealed source"
        source.write_text("before")
        out, result = self.request()
        self.assertNotEqual(out.returncode, 0)
        self.assertEqual(result["result"], "NOT_RUN")
        self.assertIsNone(result["exit_code"])
        source.unlink()
        self.verifier('echo changed > "unsealed source"; echo RESULT=pass; exit 0')
        out, result = self.request(rid="mutated")
        self.assertNotEqual(out.returncode, 0)
        self.assertEqual((result["result"], result["exit_code"]), ("fail", 0))
        self.assertIn("post-verification source check", result["error"])
        self.assertEqual(self.collect()[0]["gate"]["result"], "fail")

    def test_fault_control_failure_releases_slot_preserving_exit_and_diagnostics(self):
        self.verifier("""
slot="$SW_ROOT/.run/test-slot"
mkdir "$slot"
trap 'rmdir "$slot"; echo "slot released"' EXIT
echo "fault control assertion failed"
exit 17
""")
        out, result = self.request()
        self.assertNotEqual(out.returncode, 0)
        self.assertEqual((result["result"], result["exit_code"]), ("fail", 17))
        self.assertFalse((self.root / ".run/test-slot").exists())
        log = pathlib.Path(result["log"]).read_text()
        self.assertIn("fault control assertion failed", log)
        self.assertIn("slot released", log)

    def test_not_run_marker_remains_visible_even_with_a_zero_driver_exit(self):
        self.verifier('echo "fixture unavailable"; echo RESULT=NOT_RUN')
        out, result = self.request()
        self.assertNotEqual(out.returncode, 0)
        self.assertEqual((result["result"], result["exit_code"]), ("NOT_RUN", 0))
        self.assertEqual(self.collect()[0]["gate"]["result"], "NOT_RUN")

    def test_replay_collection_handoff_and_terminal_states(self):
        out, result = self.request()
        self.assertEqual(out.returncode, 0, result)
        self.assertEqual(self.collect()[0]["gate"]["delivery"], "fresh")
        out, repeated = self.request()
        self.assertEqual(out.returncode, 0, repeated)
        self.assertEqual(repeated, {**result, "delivery": "replayed"})
        self.handoff(result)
        self.assertEqual(self.collect(merge=True)[0]["state"], "DONE")
        self.assertEqual(self.collect(merge=True)[0]["state"], "DONE")
        metrics = self.root / "docs/process/metrics/tiers.jsonl"
        self.assertEqual(len(metrics.read_text().splitlines()), 1)
        for state in ("collected", "closed"):
            self.set_allocation(state=state)
            self.assertEqual(self.collect(), [])

    def test_tampered_log_and_missing_receipt_cannot_complete_a_candidate(self):
        out, result = self.request()
        self.assertEqual(out.returncode, 0, result)
        self.handoff(result)
        log = pathlib.Path(result["log"])
        log.write_text(log.read_text() + "RESULT=pass\n")
        self.assertEqual(self.collect()[0]["state"], "CANDIDATE-UNVERIFIED")
        (self.run_dir / "gate-bounded.json").unlink()
        self.assertEqual(self.collect()[0]["state"], "CANDIDATE-UNVERIFIED")

    def test_adding_source_with_handoff_does_not_reuse_checkpoint_evidence(self):
        out, result = self.request()
        self.assertEqual(out.returncode, 0, result)
        self.handoff(result, commit=False)
        (self.wt / "new source").write_text("unchecked")
        self.commit()
        self.assertEqual(self.collect()[0]["state"], "STALE-HANDOFF")

    def test_expect_passed_rejects_zero_wrong_skipped_and_incomplete_observations(self):
        start = {"Action": "start", "Package": "p"}
        run = {"Action": "run", "Package": "p", "Test": "TestBoundary"}
        passed = {**run, "Action": "pass"}
        skipped = {**run, "Action": "skip"}
        end = {"Action": "pass", "Package": "p"}
        for index, (events, expected, status) in enumerate([
            ([start, run, {**run, "Action": "pause"}, {**run, "Action": "cont"}, passed, end], 1, "passed"),
            ([start, end], 1, "selection_failed"),
            ([start, run, passed, end], 2, "selection_failed"),
            ([start, run, skipped, end], 1, "selection_failed"),
            ([start, run], 1, "analyzer_failed"),
        ]):
            with self.subTest(status=status, index=index):
                log = self.root / f"selected-{index}.log"
                payload = '\n'.join(map(json.dumps, events))
                out = subprocess.run([sys.executable, str(PKG / "scripts/run_logged_check.py"),
                                      "--log", str(log), "--summary", "go-json",
                                      "--expect-passed", str(expected), "--", sys.executable,
                                      "-c", "import sys; print(sys.argv[1])", payload],
                                     text=True, capture_output=True)
                receipt = json.loads(out.stdout)
                self.assertEqual(receipt["status"], status, receipt)
                self.assertEqual(receipt["raw_exit_code"], 0)
                self.assertEqual(out.returncode, 0 if status == "passed" else 2)
