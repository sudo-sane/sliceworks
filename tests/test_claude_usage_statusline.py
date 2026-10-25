# sliceworks 0.8.8. The Claude status line recorder: readings from rate_limits into usage-claude.jsonl, throttled,
# inert outside an adopted project, never failing the line.
import json, pathlib, subprocess, sys, tempfile, unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "claude-usage-statusline.py"


def run(data, cwd):
    r = subprocess.run([sys.executable, "-I", str(SCRIPT)], input=json.dumps(data) if isinstance(data, dict) else data,
                       capture_output=True, text=True, cwd=cwd)
    return r.returncode, r.stdout.strip()


def status(root, five=14.2, week=35.0, reset=1792000000):
    return {"model": {"display_name": "Opus"}, "workspace": {"project_dir": str(root)},
            "rate_limits": {"five_hour": {"used_percentage": five, "resets_at": reset - 3600},
                            "seven_day": {"used_percentage": week, "resets_at": reset}}}


class StatusLine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        (self.root / ".sliceworks").mkdir()
        (self.root / ".sliceworks" / "config.env").write_text("SW_STATE_DIR=state   # comment\n")
        self.file = self.root / "state" / "metrics" / "usage-claude.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def rows(self):
        return [json.loads(l) for l in self.file.read_text().splitlines()] if self.file.exists() else []

    def test_writes_one_reading_in_the_usage_shape(self):
        rc, out = run(status(self.root), self.root)
        self.assertEqual((rc, out), (0, "Opus · 5h 14% · 7d 35%"))
        [row] = self.rows()
        self.assertEqual((row["runtime"], row["event"], row["weekly_pct"], row["five_hour_pct"]), ("claude", "tick", 35.0, 14.2))
        self.assertEqual(row["weekly_reset"], "2026-10-14T17:46:40Z")
        self.assertRegex(row["at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_unchanged_values_are_throttled_and_a_change_is_written(self):
        run(status(self.root), self.root)
        run(status(self.root), self.root)
        self.assertEqual(len(self.rows()), 1)
        run(status(self.root, week=36.0), self.root)
        self.assertEqual([r["weekly_pct"] for r in self.rows()], [35.0, 36.0])

    def test_inert_outside_a_project_and_without_rate_limits(self):
        with tempfile.TemporaryDirectory() as other:
            rc, out = run(status(other), other)
            self.assertEqual((rc, out), (0, "Opus · 5h 14% · 7d 35%"))
            self.assertEqual(list(pathlib.Path(other).iterdir()), [])
        rc, out = run({"model": {"display_name": "Opus"}, "workspace": {"project_dir": str(self.root)}}, self.root)
        self.assertEqual((rc, out), (0, "Opus · 5h — · 7d —"))
        self.assertEqual(self.rows(), [])

    def test_bad_input_never_fails_the_line(self):
        self.assertEqual(run("not json", self.root), (0, "5h — · 7d —"))
        bad = status(self.root)
        bad["rate_limits"]["seven_day"]["used_percentage"] = "35"
        rc, _ = run(bad, self.root)
        self.assertEqual(rc, 0)
        self.assertIsNone(self.rows()[0]["weekly_pct"])


if __name__ == "__main__":
    unittest.main()
