# sliceworks 0.6.0. The collector reads completion from artifacts: pid, logs, branch head, handoff.
import contextlib, importlib.util, io, json, os, pathlib, subprocess, tempfile, unittest

HERE = pathlib.Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("collect", HERE.parent / "scripts" / "collect.py")
collect = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(collect)


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), "-c", "user.email=t@t", "-c", "user.name=t", *args], check=True, capture_output=True)


def run(root):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        collect.main(["--root", str(root)])
    return buf.getvalue()


class Collector(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = pathlib.Path(self.tmp.name)
        git(self.root, "init", "-q"); (self.root / "a").write_text("a"); git(self.root, "add", "-A"); git(self.root, "commit", "-qm", "base")
        (self.root / ".sliceworks").mkdir(); (self.root / ".sliceworks/config.env").write_text("SW_STATE_DIR=docs/process\n")
        (self.root / "docs/process/allocations").mkdir(parents=True); (self.root / "outputs/slices/slice-01").mkdir(parents=True)
        self.base = subprocess.run(["git", "-C", str(self.root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        self.wt = self.root / "wt"; git(self.root, "worktree", "add", "-q", str(self.wt), "-b", "slice/01")
        self.alloc = {"id": "alloc-slice-01-r1", "slice": "slice-01", "role": "slice-implementer", "worker": {"kind": "chat", "runtime": "codex", "id": "t1"},
                      "execution": {"pid_file": ".run/slice-01.pid", "handles": [], "log_dir": "outputs/slices/slice-01"}, "worktree": "wt", "branch": "slice/01",
                      "base": self.base, "allowed_paths": ["src/"], "completion": "rows pass", "required_artifacts": ["handoff", "tier-log"], "opened": "2026-01-01T00:00:00Z", "state": "open"}
        (self.root / "docs/process/allocations/alloc-slice-01-r1.json").write_text(json.dumps(self.alloc))

    def tearDown(self):
        self.tmp.cleanup()

    def handoff(self, result="CANDIDATE", head=None, verification="pass"):
        head = head or subprocess.run(["git", "-C", str(self.wt), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        d = self.wt / "docs/process/handoffs"; d.mkdir(parents=True, exist_ok=True)
        (d / "alloc-slice-01-r1.md").write_text(f"---\nallocation: alloc-slice-01-r1\nresult: {result}\nhead: {head}\nbase: {self.base}\nverification: {{tier: t1, log: outputs/slices/slice-01/t1-x.log, result: {verification}}}\n---\n# Handoff\n")

    def test_stopped_without_handoff(self):
        self.assertIn("STOPPED-NO-HANDOFF", run(self.root))

    def test_live_pid_is_running(self):
        (self.root / ".run").mkdir(); (self.root / ".run/slice-01.pid").write_text(str(os.getpid()))
        self.assertIn("RUNNING", run(self.root))

    def test_log_without_result_is_running(self):
        (self.root / "outputs/slices/slice-01/t1-20260101T000000Z.log").write_text("step 1 ...\n")
        self.assertIn("RUNNING", run(self.root))
        (self.root / "outputs/slices/slice-01/t1-20260101T000000Z.log").write_text("step 1 ...\nRESULT=pass\n")
        self.assertNotIn("RUNNING", run(self.root))

    def log_pass(self):
        (self.root / "outputs/slices/slice-01/t1-x.log").write_text("step 1\nRESULT=pass\n")

    def test_candidate_with_pass_is_done(self):
        self.handoff(); self.log_pass(); self.assertIn("DONE", run(self.root))

    def test_candidate_claim_without_log_is_unverified(self):
        self.handoff(); self.assertIn("CANDIDATE-UNVERIFIED", run(self.root)); self.assertIn("not found", run(self.root))

    def test_candidate_claim_contradicted_by_log_is_unverified(self):
        self.handoff(); (self.root / "outputs/slices/slice-01/t1-x.log").write_text("RESULT=fail\n")
        self.assertIn("CANDIDATE-UNVERIFIED", run(self.root))

    def test_tiers_row_must_match_head_when_tiers_exist(self):
        self.handoff(); self.log_pass()
        head = subprocess.run(["git", "-C", str(self.wt), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        (self.root / "docs/process/metrics").mkdir(parents=True)
        (self.root / "docs/process/metrics/tiers.jsonl").write_text(json.dumps({"tier": "t1", "head": "deadbeef", "result": "pass"}) + "\n")
        self.assertIn("CANDIDATE-UNVERIFIED", run(self.root))
        (self.root / "docs/process/metrics/tiers.jsonl").write_text(json.dumps({"tier": "t1", "head": head[:8], "result": "pass"}) + "\n")
        self.assertIn("DONE", run(self.root))

    def test_scoped_tier_requires_named_log_full_source_base_and_actual_exit(self):
        self.handoff()
        self.log_pass()
        self.alloc["accepted_base"] = self.base
        (self.root / "docs/process/allocations/alloc-slice-01-r1.json").write_text(json.dumps(self.alloc))
        tiers = self.root / "docs/process/metrics/tiers.jsonl"
        tiers.parent.mkdir()
        row = {"head": self.base[:8], "head_full": self.base, "base": self.base,
               "accepted_base": self.base, "slice": "slice-01", "tier": "t1", "result": "pass",
               "log": "outputs/slices/slice-01/t1-x.log", "exit_code": 0}
        for mismatch in ({"log": "different.log"}, {"head_full": "a" * 40}, {"base": "a" * 40},
                         {"accepted_base": "a" * 40}, {"exit_code": 8}, {"exit_code": None}):
            with self.subTest(mismatch=mismatch):
                tiers.write_text(json.dumps({**row, **mismatch}) + "\n")
                self.assertIn("CANDIDATE-UNVERIFIED", run(self.root))
        tiers.write_text(json.dumps(row) + "\n")
        self.assertIn("DONE", run(self.root))

    def test_queue_marker_is_queued(self):
        self.alloc["execution"]["queue_marker"] = ".run/pg-queue/slice-01"; (self.root / "docs/process/allocations/alloc-slice-01-r1.json").write_text(json.dumps(self.alloc))
        (self.root / ".run/pg-queue").mkdir(parents=True); (self.root / ".run/pg-queue/slice-01").write_text("ticket")
        self.assertIn("QUEUED", run(self.root))

    def test_unregistered_evidence_is_reported(self):
        self.alloc["state"] = "closed"; (self.root / "docs/process/allocations/alloc-slice-01-r1.json").write_text(json.dumps(self.alloc))
        (self.root / ".run").mkdir(exist_ok=True); (self.root / ".run/other.pid").write_text(str(os.getpid()))
        (self.root / "outputs/slices/slice-09").mkdir(parents=True); (self.root / "outputs/slices/slice-09/t1-y.log").write_text("running\n")
        out = run(self.root)
        self.assertIn("ALLOC none open", out); self.assertIn("UNREGISTERED worktree wt", out); self.assertIn("UNREGISTERED pid .run/other.pid alive", out); self.assertIn("UNREGISTERED log outputs/slices/slice-09/t1-y.log", out)

    def test_ids_are_printed(self):
        self.alloc["worker"]["chat_id"] = "thread-9"; self.alloc["execution"]["session_id"] = "sess-3"; (self.root / "docs/process/allocations/alloc-slice-01-r1.json").write_text(json.dumps(self.alloc))
        self.assertIn("[chat=thread-9 session=sess-3]", run(self.root))

    def test_candidate_without_pass_is_unverified(self):
        self.handoff(verification="NOT_RUN"); self.assertIn("CANDIDATE-UNVERIFIED", run(self.root))

    def test_blocked_and_hold_come_from_the_handoff(self):
        self.handoff(result="BLOCKED"); self.assertIn("ALLOC alloc-slice-01-r1 BLOCKED", run(self.root))
        self.handoff(result="HOLD"); self.assertIn("ALLOC alloc-slice-01-r1 HOLD", run(self.root))

    def test_branch_moved_past_handoff_is_stale(self):
        self.handoff()
        (self.wt / "b").write_text("b"); git(self.wt, "add", "-A"); git(self.wt, "commit", "-qm", "more")
        self.assertIn("STALE-HANDOFF", run(self.root))

    def test_closed_allocations_are_skipped_and_missing_worktree_reported(self):
        self.alloc["state"] = "closed"; (self.root / "docs/process/allocations/alloc-slice-01-r1.json").write_text(json.dumps(self.alloc))
        self.assertIn("none open", run(self.root))
        self.alloc["state"] = "open"; self.alloc["worktree"] = "nowhere"; (self.root / "docs/process/allocations/alloc-slice-01-r1.json").write_text(json.dumps(self.alloc))
        self.assertIn("MISSING-WORKTREE", run(self.root))


class WorkerMetrics(unittest.TestCase):
    def test_merge_is_explicit_idempotent_and_keeps_partial_lines_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            source = root / "custom-run/codex/alloc-1/metrics/tiers.jsonl"
            source.parent.mkdir(parents=True)
            row = {"head_full": "a" * 40, "result": "pass", "tier": "t1"}
            source.write_text(json.dumps(row) + "\n" + '{"unfinished":')
            self.assertEqual(collect.merge_worker_metrics(root, "docs/process", "custom-run"), 1)
            self.assertEqual(collect.merge_worker_metrics(root, "docs/process", "custom-run"), 0)
            dest = root / "docs/process/metrics/tiers.jsonl"
            self.assertEqual([json.loads(line) for line in dest.read_text().splitlines()], [row])
            source.write_text(source.read_text() + 'true}\n')
            self.assertEqual(collect.merge_worker_metrics(root, "docs/process", "custom-run"), 1)
            self.assertEqual(len(dest.read_text().splitlines()), 2)

    def test_non_object_and_symlink_metrics_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            source = root / ".run/codex/alloc-1/metrics/tiers.jsonl"
            source.parent.mkdir(parents=True)
            source.write_text('[]\n')
            with self.assertRaises(ValueError):
                collect.merge_worker_metrics(root, "docs/process", ".run")
            source.unlink()
            other = root / "other"; other.write_text('{}\n')
            source.symlink_to(other)
            with self.assertRaises(ValueError):
                collect.merge_worker_metrics(root, "docs/process", ".run")


if __name__ == "__main__":
    unittest.main()
