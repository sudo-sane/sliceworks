"""Exercise the verifier, collector and selector against disposable Git worktrees."""

import hashlib
import json
import shlex
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
        request = f"gate_request: {result['request_id']}\n" if "request_id" in result else ""
        path.write_text(f"""---
allocation: {AID}
result: CANDIDATE
head: {result['head']}
base: {result['base']}
{request}verification: {{tier: t1, log: {result['log']}, result: pass}}
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
        for rid in ("active", "request", "result", "AcTiVe", "ReQuEsT", "ReSuLt"):
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

    def opt_in(self, extra=""):
        self.config = self.root / ".sliceworks/config.env"
        with self.config.open("a") as stream:
            stream.write("SW_VERIFY_CADENCE=candidate\n" + extra)
        self.counter = self.root / "gate-invocations"
        self.verifier(f"echo run >> {shlex.quote(str(self.counter))}\necho RESULT=pass")

    def stop(self, adapter, allocation=AID):
        event = {"cwd": str(self.wt), "stop_hook_active": False}
        env = self.environment()
        if adapter == "codex":
            event.update(turn_id="turn", hook_event_name="Stop")
            env.update(SW_ROLE="slice-implementer", SW_ALLOCATION=allocation)
        else:
            event.update(agent_type="sliceworks:slice-implementer", hook_event_name="SubagentStop")
        run = subprocess.run(["sh", str(PKG / "hooks/implementer-stop.sh")],
                             cwd=self.root, env=env, input=json.dumps(event),
                             capture_output=True, text=True, timeout=20, check=True)
        return json.loads(run.stdout).get("decision") if run.stdout else None

    def direct_gate(self, head):
        command = [str(self.verify), "--cwd", str(self.wt), "--slice", "slice-07",
                   "--base", self.base, "t1"]
        log = self.root / "direct.log"
        with log.open("w") as stream:
            run = subprocess.run(command, cwd=self.wt, stdout=stream, check=True)
        row = {"head_full": head, "base": self.base, "accepted_base": self.base,
               "slice": "slice-07", "allocation": AID, "worktree": str(self.wt),
               "tier": "t1", "state": "executed", "result": "pass", "exit_code": run.returncode, "log": str(log),
               "command": shlex.join(command), "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
               "inputs": {"config_sha256": hashlib.sha256(self.config.read_bytes()).hexdigest(),
                          "verifier_sha256": hashlib.sha256(self.verify.read_bytes()).hexdigest()}}
        self.tiers = self.root / "docs/process/metrics/tiers.jsonl"
        self.tiers.write_text(json.dumps(row) + "\n")
        return {"head": head, "base": self.base, "log": str(log)}

    def test_opt_in_stop_and_committed_handoff_use_one_gate(self):
        self.opt_in()
        (self.wt / "source").write_text("first checkpoint")
        self.commit()
        for adapter in ("codex", "claude"):
            self.assertIsNone(self.stop(adapter))
            self.assertEqual(self.collect()[0]["state"], "STOPPED-NO-HANDOFF")
            self.assertFalse(self.counter.exists())
        (self.wt / "source").write_text("completed outcome")
        head = self.commit()
        result = self.direct_gate(head)
        self.handoff(result, commit=False)
        self.assertEqual(self.collect()[0]["state"], "CANDIDATE-UNVERIFIED")
        self.assertEqual(self.stop("claude"), "block")
        self.commit()
        for adapter in ("claude", "codex"):
            self.assertIsNone(self.stop(adapter))
            complete = self.collect()[0]
            self.assertEqual(complete["state"], "DONE")
            self.assertIn(head, complete["detail"])
        self.assertEqual(self.counter.read_text().splitlines(), ["run"])
        (self.wt / "source").write_text("repair in progress")
        self.assertEqual(self.collect()[0]["state"], "STALE-HANDOFF")
        self.assertIsNone(self.stop("codex"))
        self.assertEqual(self.counter.read_text().splitlines(), ["run"])

    def test_opt_in_broker_receipt_and_queued_request(self):
        self.opt_in()
        (self.run_dir / "gate-active.json").write_text("{}")
        self.assertEqual(self.collect()[0]["state"], "QUEUED")
        (self.run_dir / "gate-active.json").unlink()
        out, result = self.request()
        self.assertEqual(out.returncode, 0, result)
        self.handoff(result)
        self.assertEqual(self.collect()[0]["state"], "DONE")
        self.assertIsNone(self.stop("codex"))
        self.assertEqual(self.counter.read_text().splitlines(), ["run"])
        with self.config.open("a") as stream:
            stream.write("# changed verifier configuration\n")
        self.assertEqual(self.collect()[0]["state"], "CANDIDATE-UNVERIFIED")
        self.assertEqual(self.stop("codex"), "block")

    def test_opt_in_separate_required_check_cannot_hide_behind_green_t1(self):
        self.opt_in()
        out, result = self.request()
        self.assertEqual(out.returncode, 0, result)
        self.handoff(result)
        with self.config.open("a") as stream:
            stream.write('SW_PREHANDOFF_CMD="exit 7"\n')
        self.assertEqual(self.collect()[0]["state"], "CANDIDATE-UNVERIFIED")
        self.assertEqual(self.stop("codex"), "block")
        out, refused = self.request(rid="separate")
        self.assertNotEqual(out.returncode, 0, refused)
        self.assertEqual(refused["result"], "NOT_RUN")

    def test_opt_in_required_verifier_failure_blocks_review_despite_pass_marker(self):
        self.opt_in()
        self.verifier("echo RESULT=pass\nexit 7")
        out, result = self.request()
        self.assertNotEqual(out.returncode, 0, result)
        self.assertEqual((result["result"], result["exit_code"]), ("fail", 7))
        self.handoff(result)
        self.assertEqual(self.collect()[0]["state"], "CANDIDATE-UNVERIFIED")
        self.assertEqual(self.stop("codex"), "block")

    def test_opt_in_direct_invalid_evidence_cannot_enter_review(self):
        self.opt_in()
        result = self.direct_gate(self.base)
        self.handoff(result)
        row = json.loads(self.tiers.read_text())
        for change in (
            {"exit_code": 3}, {"result": "NOT_RUN"}, {"state": "NOT_RUN"}, {"head_full": "a" * 40},
            {"command": "different-verifier t1"}, {"log_sha256": "a" * 64},
            {"accepted_base": "a" * 40}, {"inputs": {}},
        ):
            with self.subTest(change=change):
                self.tiers.write_text(json.dumps({**row, **change}) + "\n")
                self.assertEqual(self.collect()[0]["state"], "CANDIDATE-UNVERIFIED")
        self.tiers.unlink()
        self.assertEqual(self.collect()[0]["state"], "CANDIDATE-UNVERIFIED")

    def test_opt_in_ambiguous_identity_keeps_legacy_check_and_hold(self):
        self.opt_in()
        result = self.direct_gate(self.base)
        self.handoff(result)
        other = "alloc-slice-07-r2"
        self.alloc(other, {"role": "slice-implementer", "worktree": str(self.wt),
                           "branch": "slice/07", "state": "open"})
        for adapter in ("codex", "claude"):
            self.assertIsNone(self.stop(adapter))
        self.assertEqual(self.counter.read_text().splitlines(), ["run"] * 3)
        self.assertTrue(all(item["state"] != "DONE" for item in self.collect()))
        (self.root / "docs/process/allocations" / (other + ".json")).unlink()
        marker = self.wt / ".blocked"
        marker.write_text("HOLD waiting\n")
        self.verifier("exit 8")
        self.assertEqual(self.stop("codex"), "block")
        self.assertEqual(self.collect()[0]["state"], "HOLD")

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
