# sliceworks 0.8.4. Tests for scripts/check-design-docs.py: each lint turns red on its failure and stays green otherwise.
import contextlib, importlib.util, io, os, pathlib, shutil, subprocess, tempfile, unittest

HERE = pathlib.Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("cdd", HERE.parent / "scripts" / "check-design-docs.py")
cdd = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(cdd)


def run(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True)


class DesignDocLints(unittest.TestCase):
    HEADER = "| file | governs | status | last reviewed | notes |\n|---|---|---|---|---|\n"
    PIVOT = "# Decisions\n\n## Decisions\n\n### D-003 · Pivot to teams\n- 2026-10-10 · owner answer · class A2 · **decided** · pivot · veto by 2026-10-12\n- Decision: the promise changes from one user to a team.\n"
    NOT_PIVOT = "# Decisions\n\n## Decisions\n\n### D-003 · Rename a field\n- 2026-10-10 · review slice-02 · class B · **decided**\n- Decision: rename it.\n"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = pathlib.Path(self.tmp.name)
        run(self.root, "init", "-q"); run(self.root, "config", "user.email", "t@t"); run(self.root, "config", "user.name", "t")
        (self.root / "docs/process").mkdir(parents=True); (self.root / "specs").mkdir()
        (self.root / "docs/process/ARCHITECTURE.md").write_text("# Architecture\n\n## 1\nbase\n")
        (self.root / "docs/process/INDEX.md").write_text("| file | governs | status | last reviewed | notes |\n|---|---|---|---|---|\n| ARCHITECTURE.md | design | current | 2026-10-01 | |\n")
        (self.root / "specs/events-1.md").write_text("---\nstatus: frozen\n---\n# Events 1\nno todo here\n")
        run(self.root, "add", "-A"); run(self.root, "commit", "-qm", "base")

    def tearDown(self):
        self.tmp.cleanup()

    def lint(self, **kw):
        args = ["--root", str(self.root), "--base", "HEAD~1", "--today", kw.pop("today", "2026-10-12")]
        for k, v in kw.items():
            args += [f"--{k.replace('_', '-')}", str(v)]
        return cdd.main(args)

    def test_clean_tree_passes(self):
        (self.root / "README.md").write_text("x"); run(self.root, "add", "-A"); run(self.root, "commit", "-qm", "unrelated")
        self.assertEqual(self.lint(), 0)

    def test_architecture_change_without_decision_fails(self):
        (self.root / "docs/process/ARCHITECTURE.md").write_text("# Architecture\n\n## 1\nchanged\n")
        run(self.root, "add", "-A"); run(self.root, "commit", "-qm", "edit architecture")
        self.assertEqual(self.lint(), 1)

    def test_architecture_change_citing_decision_in_lines_passes(self):
        (self.root / "docs/process/ARCHITECTURE.md").write_text("# Architecture\n\n## 1 (D-012)\nchanged\n")
        run(self.root, "add", "-A"); run(self.root, "commit", "-qm", "edit architecture")
        self.assertEqual(self.lint(), 0)

    def test_architecture_change_citing_decision_in_message_passes(self):
        (self.root / "docs/process/ARCHITECTURE.md").write_text("# Architecture\n\n## 1\nchanged\n")
        run(self.root, "add", "-A"); run(self.root, "commit", "-qm", "edit architecture per D-7")
        self.assertEqual(self.lint(), 0)

    def test_uncommitted_architecture_change_is_checked(self):
        (self.root / "docs/process/ARCHITECTURE.md").write_text("# Architecture\n\n## 1\nworking tree edit\n")
        self.assertEqual(self.lint(), 1)

    def test_stale_index_row_fails(self):
        self.assertEqual(self.lint(today="2026-12-01"), 1)
        self.assertEqual(self.lint(today="2026-12-01", limit_days=90), 0)

    def test_current_row_not_reviewed_since_pivot_fails(self):
        (self.root / "docs/process/DECISIONS.md").write_text(self.PIVOT)
        self.assertEqual(self.lint(), 1)  # ARCHITECTURE.md reviewed 2026-10-01, pivot 2026-10-10
        (self.root / "docs/process/INDEX.md").write_text(self.HEADER + "| ARCHITECTURE.md | design | current | 2026-10-11 | |\n| archive/2026-10-10-SPARK.md | the old idea | archived (D-003) | 2026-09-01 | |\n")
        self.assertEqual(self.lint(), 0)  # reviewed after the pivot; the archived row is exempt

    def test_undated_current_row_after_pivot_fails(self):
        (self.root / "docs/process/DECISIONS.md").write_text(self.PIVOT)
        (self.root / "docs/process/INDEX.md").write_text(self.HEADER + "| ARCHITECTURE.md | design | current | | |\n")
        self.assertEqual(self.lint(), 1)

    def test_decision_without_pivot_marker_requires_no_review(self):
        (self.root / "docs/process/DECISIONS.md").write_text(self.NOT_PIVOT)
        self.assertEqual(self.lint(), 0)

    def test_brief_referencing_archived_document_fails(self):
        (self.root / "docs/process/slices").mkdir()
        brief = self.root / "docs/process/slices/slice-01.md"
        brief.write_text("# Brief\nRead docs/process/archive/2026-10-10-ARCHITECTURE.md first.\n")
        self.assertEqual(self.lint(), 1)
        brief.write_text("# Brief\nThe product keeps an archive/ of exports; see ARCHITECTURE.md.\n")
        self.assertEqual(self.lint(), 0)

    def test_frozen_spec_with_todo_fails(self):
        (self.root / "specs/events-1.md").write_text("---\nstatus: frozen\n---\n# Events 1\nTODO decide\n")
        self.assertEqual(self.lint(), 1)
        (self.root / "specs/events-1.md").write_text("---\nstatus: draft\n---\n# Events 1\nTODO decide\n")
        self.assertEqual(self.lint(), 0)


class BacklogLint(unittest.TestCase):
    """Check 6 on the dashboard fixtures: `increments` has a range heading and increments 2 to 5 without a section."""
    FIX = HERE / "fixtures" / "dashboard"

    def copy(self, name):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name) / name
        shutil.copytree(self.FIX / name, root)
        return root

    def test_fixtures_with_a_section_per_increment_pass(self):
        for name in ("run", "adopted"):  # adopted: increments 0 and 1 closed before adoption are exempt
            ok, msg = cdd.check_backlog(self.copy(name), "docs/process")
            self.assertTrue(ok, f"{name}: {msg}")

    def test_range_heading_and_missing_sections_fail(self):
        ok, msg = cdd.check_backlog(self.copy("increments"), "docs/process")
        self.assertFalse(ok)
        self.assertIn("## Increments 4 to 5", msg)
        self.assertIn("2 (MILESTONES.md), 3 (FEATURES.json), 4 (FEATURES.json, MILESTONES.md), 5 (NEEDS-HUMAN.md)", msg)

    def test_negative_control_the_other_checks_were_blind(self):
        """Without check 6 the defective fixture passes the lint: only the new check catches it."""
        root = self.copy("increments")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cdd.main(["--root", str(root), "--today", "2026-10-15"]), 1)
            real = cdd.check_backlog
            cdd.check_backlog = lambda root, state_dir: (True, "backlog: skipped")
            try:
                self.assertEqual(cdd.main(["--root", str(root), "--today", "2026-10-15"]), 0)
            finally:
                cdd.check_backlog = real

    def test_one_section_per_increment_passes(self):
        root = self.copy("increments")
        p = root / "docs/process/BACKLOG.md"
        sections = "".join(f"## Increment {n}: later {n}\n\nExit demo: demo {n}. Scenarios: none. Human acts: none.\n\n"
                           f"Proposed slices (candidates): a; b.\n\n" for n in (2, 3, 4, 5))
        p.write_text(p.read_text().split("## Increments 4 to 5")[0] + sections)
        ok, msg = cdd.check_backlog(root, "docs/process")
        self.assertTrue(ok, msg)
        p.write_text(p.read_text().replace("## Increment 3: later 3", "## Increment 3"))
        ok, msg = cdd.check_backlog(root, "docs/process")
        self.assertFalse(ok, "a heading without a title is unreadable")
        self.assertIn("## Increment 3", msg)


if __name__ == "__main__":
    unittest.main()
