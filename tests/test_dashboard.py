# sliceworks 0.7.0. The dashboard renders the first run's page from any adopted project: tests on the parsed page
# structure and on the computed numbers, never on substrings of the HTML.
import contextlib, datetime as dt, html.parser, io, json, pathlib, re, shutil, subprocess, sys, tempfile, unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from dashboard import collect, compute, render  # noqa: E402
from dashboard.__main__ import main  # noqa: E402

FIX = HERE / "fixtures" / "dashboard"
NOW = "2026-10-15T12:00:00Z"
TEMPLATE_STATES = ("proposed", "draft", "ready", "active", "repair", "blocked", "testing", "review", "waiting", "merged",
                   "green", "paused", "stopped", "hold", "cut")


class Node:
    def __init__(self, tag, attrs, parent=None):
        self.tag, self.attrs, self.parent, self.children, self.text = tag, dict(attrs), parent, [], ""

    @property
    def classes(self):
        return set((self.attrs.get("class") or "").split())

    def all(self, tag=None, cls=None):
        out = []
        for c in self.children:
            if (tag is None or c.tag == tag) and (cls is None or set(cls.split()) <= c.classes):
                out.append(c)
            out.extend(c.all(tag, cls))
        return out

    def first(self, tag=None, cls=None):
        got = self.all(tag, cls)
        return got[0] if got else None

    def text_all(self):
        return self.text + "".join(c.text_all() for c in self.children)


class Tree(html.parser.HTMLParser):
    VOID = {"meta", "br", "img", "input", "link", "hr"}

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {})
        self.cur = self.root
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs, self.cur)
        self.cur.children.append(n)
        if tag not in self.VOID:
            self.cur = n

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.text += data


def copy_fixture(name):
    tmp = tempfile.TemporaryDirectory()
    root = pathlib.Path(tmp.name).resolve() / name
    shutil.copytree(FIX / name, root)
    return tmp, root


def render_fixture(root, *extra):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["--root", str(root), "--now", NOW, "--no-history", *extra])
    out = pathlib.Path(buf.getvalue().strip().split("dashboard: ", 1)[1])
    return rc, out, Tree(out.read_text(encoding="utf-8")).root


class Parsers(unittest.TestCase):
    def test_table_keeps_empty_cells_and_inner_pipes(self):
        rows = collect.table("| id | state | note |\n|---|---|---|\n| slice-01 a b | | `x|y` |\n")
        self.assertEqual(rows, [{"id": "slice-01 a b", "state": "", "note": "`x|y`"}])

    def test_named_slice_ids_split(self):
        self.assertEqual(collect.split_id("slice-01 land-inflight-set (process)"), ("slice-01", "land-inflight-set (process)"))
        self.assertEqual(collect.split_id("slice-48g"), ("slice-48g", ""))

    def test_timestamps_iso_and_epoch(self):
        a = collect.parse_iso("2026-10-15T13:18Z")
        self.assertEqual(a, dt.datetime(2026, 10, 15, 13, 18, tzinfo=dt.timezone.utc))
        self.assertEqual(collect.parse_iso(int(a.timestamp())), a)
        self.assertEqual(collect.parse_iso("2026-10-09T04:31Z e406d167"), dt.datetime(2026, 10, 9, 4, 31, tzinfo=dt.timezone.utc))
        self.assertIsNone(collect.parse_iso("-"))

    def test_config_strips_quotes_and_comments(self):
        tmp, root = copy_fixture("adopted")
        with tmp:
            cfg = collect.load_config(root)
        self.assertEqual(cfg["SW_MONEY_CAP"], "15")
        self.assertEqual(cfg["SW_DASHBOARD_OUT"], "build/sliceworks/dashboard.html")

    def test_decisions_and_questions(self):
        tmp, root = copy_fixture("run")
        with tmp:
            d = {x["id"]: x for x in collect.decisions_md((root / "docs/process/DECISIONS.md").read_text())}
        self.assertEqual((d["D-001"]["class"], d["D-001"]["status"], d["D-001"]["veto_by"]), ("A2", "defaulted", "2026-10-17"))
        self.assertTrue(d["Q-001"]["question"])
        self.assertEqual(d["Q-001"]["due"], "2026-10-20")


class Vocabulary(unittest.TestCase):
    def test_every_template_state_is_known(self):
        for st in TEMPLATE_STATES:
            self.assertTrue(compute.known(st), st)

    def test_every_method_slice_state_is_known(self):
        text = (HERE.parent / "method/03-lifecycles.md").read_text().split("## Slice\n", 1)[1].split("\n## ", 1)[0]
        states = re.findall(r"^\| `([a-z_]+)` \|", text, re.M)
        self.assertGreaterEqual(len(states), 13, "the chapter 3 slice table was not found")
        for st in states:
            self.assertTrue(compute.known(st), st)

    def test_every_kind_has_a_chip_style(self):
        for kind in {k for _, k, _ in compute.STATES.values()} | {"unknown"}:
            if kind != "idle":
                self.assertRegex(render.CSS, r"\.chip\.%s\b" % kind)

    def test_credit(self):
        self.assertEqual(compute.credit({"state": "merged", "green": "2026-10-14T10:50Z"}), 1.0)
        self.assertEqual(compute.credit({"state": "merged", "green": "-"}), 0.9)
        self.assertIsNone(compute.credit({"state": "cut"}))

    def test_zone(self):
        t = dt.datetime(2026, 10, 15, 12, tzinfo=dt.timezone.utc)
        self.assertEqual(t.astimezone(compute.zone("+03:00")).hour, 15)
        self.assertEqual(t.astimezone(compute.zone("UTC+3")).hour, 15)
        self.assertEqual(t.astimezone(compute.zone("UTC")).hour, 12)


class NeedsAndLinks(unittest.TestCase):
    LINKS = {"base": "", "state_rel": "docs/process", "page_to_root": "../.."}

    def test_markdown_link_resolves_from_the_state_dir(self):
        out = render.linkify("Review [the patch](../../outputs/x/p.patch) now", self.LINKS)
        self.assertIn('<a href="../../outputs/x/p.patch">the patch</a>', out)
        based = render.linkify("[d](DECISIONS.md)", dict(self.LINKS, base="https://example.test/r/blob/main/"))
        self.assertIn('href="https://example.test/r/blob/main/docs/process/DECISIONS.md"', based)
        self.assertIn('href="https://x.test/a"', render.linkify("[a](https://x.test/a)", self.LINKS))

    def test_slice_ids_link_to_cards_and_missing_cards_unlink(self):
        out = render.linkify("unblocks slice-01 and slice99 <b>", self.LINKS)
        self.assertIn('<a class="sref" href="#s-slice-01">slice-01</a>', out)
        self.assertIn('&lt;b&gt;', out)
        page = render.unlink_missing('<article id="s-slice-01"></article>' + out)
        self.assertIn('href="#s-slice-01"', page)
        self.assertNotIn('href="#s-slice-99"', page)
        self.assertIn("slice99", page)

    def test_needs_item_expands_to_the_full_act(self):
        act = "word " * 60 + "[the patch](p.patch)"
        li = render.nh_item({"id": "NH-07", "act": act, "unblocks": "slice-02", "urgency": "now", "added": "2026-10-15",
                             "increment": "2"}, self.LINKS, 40, True)
        self.assertIn('<details class="nh">', li)
        self.assertIn("…", li.split("</summary>")[0])
        body = li.split("</summary>")[1]
        self.assertIn('href="../../docs/process/p.patch"', body)
        self.assertIn('href="#s-slice-02"', body)
        self.assertIn('class="urgent"', li)


class RunFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp, cls.root = copy_fixture("run")
        cls.rc, cls.out, cls.page = render_fixture(cls.root)
        cls.snap = collect.snapshot(cls.root, collect.load_config(cls.root))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_writes_into_the_state_dir_by_default(self):
        self.assertEqual(self.rc, 0)
        self.assertEqual(self.out, self.root / "docs/process/dashboard.html")
        self.assertEqual(self.page.first("title").text, "Fixture run progress")
        self.assertEqual(self.page.first("h1").text, "Fixture run")

    def test_self_contained(self):
        for n in self.page.all():
            for attr in ("src", "href"):
                v = n.attrs.get(attr) or ""
                self.assertFalse(re.match(r"(https?:)?//", v), f"{n.tag} {attr}={v}")
        self.assertIsNone(self.page.first("link"))
        style = self.page.first("style").text
        self.assertIn("prefers-color-scheme:dark", style)
        self.assertIn("prefers-reduced-motion:reduce", style)
        self.assertEqual(self.page.first("meta", None).attrs.get("charset"), "utf-8")
        self.assertTrue(any(m.attrs.get("http-equiv") == "refresh" for m in self.page.all("meta")))

    def test_tiles(self):
        tiles = self.page.first("div", "tiles")
        kinds = [t.classes for t in tiles.children]
        self.assertTrue(any("prog" in k for k in kinds))
        self.assertTrue(any("scov" in k for k in kinds))
        self.assertTrue(any("budget" in k for k in kinds))
        self.assertFalse(any("money" in k for k in kinds), "no money tile without a cap or entries")
        scov = tiles.first("a", "scov")
        self.assertEqual(scov.attrs["href"], "#d-scenarios")
        self.assertIn("M1 scenarios", scov.text_all())

    def test_holds_banner(self):
        holds = self.page.first("header", "hd").all("div", "hold")
        self.assertEqual(len(holds), 1)
        self.assertIn("staging database", holds[0].text_all())

    def test_increments(self):
        incs = self.page.all("section", "inc")
        self.assertEqual(len(incs), 3)
        closed, current, later = incs
        self.assertIn("closed", closed.classes)
        self.assertIsNotNone(closed.first("a"), "closed increment links its retro")
        cur = current.first("details")
        self.assertIn("open", cur.attrs)
        self.assertEqual(cur.attrs["id"], "d-inc-1")
        self.assertIsNotNone(current.first("div", "timeline"))
        self.assertEqual(len(later.first("ul", "plan").all("li")), 3)

    def test_slice_cards(self):
        cards = self.page.all("article", "slice")
        self.assertEqual(len(cards), 6)
        compact = [c for c in cards if "compact" in c.classes]
        self.assertEqual(len(compact), 2, "merged slices render compact")
        for c in cards:
            if "compact" in c.classes:
                continue
            steps = c.first("ol", "stepper").all("li")
            self.assertEqual(len(steps), 6)
        active = next(c for c in cards if "slice-03" in c.first("code").text)
        cur = [li for li in active.first("ol", "stepper").all("li") if "cur" in li.classes]
        self.assertEqual(cur[0].first("span").text, "Implementing")
        for chip in self.page.all("span", "chip"):
            self.assertNotIn("unknown", chip.classes)

    def test_timeline_marks_live_work(self):
        current = next(s for s in self.page.all("section", "inc") if s.first("details").attrs.get("id") == "d-inc-1")
        bars = current.first("div", "timeline").all("i", "tl")
        self.assertTrue(any({"impl", "live"} <= b.classes for b in bars))
        self.assertTrue(any("rev" in b.classes for b in bars))

    def test_owner_view(self):
        cards = [c for two in self.page.all("div", "two") for c in two.children]
        heads = [c.first("h4").text for c in cards]
        self.assertIn("Needs a human (1 open)", heads)
        needs = next(c for c in cards if c.first("h4").text.startswith("Needs a human"))
        self.assertTrue(needs.all("details", "nh"), "each open act expands to its full text")
        for card in self.page.all("article", "slice"):
            self.assertTrue(card.attrs.get("id", "").startswith("s-slice"), "slice cards are link targets")
        self.assertIn("Veto clocks (1 open)", heads)
        clocks = next(c for c in cards if c.first("h4").text.startswith("Veto clocks"))
        self.assertIn("D-001", clocks.text_all())
        self.assertNotIn("D-003", clocks.text_all(), "an expired veto window is not a clock")
        self.assertIn("Q-001", clocks.text_all())

    def test_ready_now(self):
        rn = compute.ready_now(self.snap)
        self.assertEqual(rn["ready"], ["slice-06 [draft]"], "slice-05 waits for slice-03")
        self.assertEqual((rn["writers"], rn["cap"]), (2, 3))

    def test_progress_and_budget(self):
        incs = compute.increments(self.snap)
        per = compute.progress(self.snap, incs, 1)
        self.assertEqual([(n, t) for n, _, t, _ in per], [(0, 2.0), (1, 4.0), (2, 3.0)])
        self.assertAlmostEqual(per[1][3], 0.25 + 0.6 + 0.05 + 0.0)
        bd = compute.budget(self.snap, per, collect.parse_iso(NOW))
        self.assertTrue(bd["known"])
        self.assertEqual((bd["hold"], bd["stop"], bd["kind"]), (80, 85, ""))

    def test_history_is_appended_outside_render(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["--root", str(self.root), "--now", NOW, "--out", str(self.root / "h.html")])
        hist = collect.jsonl(self.root / ".run" / "progress-history.jsonl")
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["t"], "2026-10-15T12:00:00+00:00")


class AdoptedFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp, cls.root = copy_fixture("adopted")
        cls.rc, cls.out, cls.page = render_fixture(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_configured_output_and_readme_title(self):
        self.assertEqual(self.out, self.root / "build/sliceworks/dashboard.html")
        self.assertEqual(self.page.first("h1").text, "Fixture Adopted")

    def test_money_tile_and_unknown_budget(self):
        tiles = self.page.first("div", "tiles")
        self.assertIn("four", tiles.classes)
        money = tiles.first("div", "money")
        self.assertIn("9.50", money.text_all())
        budget = tiles.first("div", "budget")
        self.assertIn("UNKNOWN", budget.text_all(), "no usage reading is UNKNOWN, never 0%")

    def test_closed_increments_before_adoption(self):
        incs = self.page.all("section", "inc")
        before = [s for s in incs if "before adoption" in s.text_all()]
        self.assertEqual(len(before), 2)
        self.assertEqual(len(incs), 4)
        self.assertIsNotNone(self.page.first("span", "pv1"))

    def test_named_slices_render_as_cards(self):
        cards = self.page.all("article", "slice")
        ids = [c.first("code").text for c in cards]
        self.assertEqual(ids, ["slice-01", "slice-02", "slice-03", "slice-04"])
        self.assertEqual(cards[0].first("b").text, "land-inflight-set (process)")
        for chip in self.page.all("span", "chip"):
            self.assertNotIn("unknown", chip.classes)

    def test_cut_slice_leaves_progress(self):
        snap = collect.snapshot(self.root, collect.load_config(self.root))
        per = compute.progress(snap, compute.increments(snap), 2)
        self.assertEqual([(n, t) for n, _, t, _ in per], [(2, 2.0), (3, 1.0)])

    def test_veto_clocks_and_question(self):
        cards = [c for two in self.page.all("div", "two") for c in two.children]
        clocks = next(c for c in cards if c.first("h4").text.startswith("Veto clocks"))
        self.assertEqual(clocks.first("h4").text, "Veto clocks (3 open)")
        self.assertIn("PQ-001", clocks.text_all())

    def test_human_acts_attach_to_increment_ranges(self):
        inc3 = next(s for s in self.page.all("section", "inc") if s.first("details").attrs.get("id") == "d-inc-3")
        self.assertIn("NH-02", inc3.first("div", "acts").text_all())

    def test_thinned_scenario(self):
        rows = self.page.first("table").all("tr")
        self.assertTrue(any("thinned" in r.text_all() for r in rows))


def legacy_increments(snap):
    """compute.increments as of 0.8.3, kept as the negative control: backlog sections plus closed MILESTONES rows only."""
    ms_of = {i["n"]: m["id"] for m in snap["milestones"] for i in m["increments"]}
    incs = [dict(i, milestone=ms_of.get(i["n"], ""), before=False) for i in snap["backlog"]]
    have = {i["n"] for i in incs}
    before = []
    for m in snap["milestones"]:
        for i in m["increments"]:
            if i["n"] not in have and re.match(r"(closed|done|accepted)", i["state"].strip().lower()):
                before.append({"n": i["n"], "title": i["title"], "demo": i["demo"], "planned": [], "titles": {},
                               "milestone": m["id"], "before": True, "state_text": i["state"]})
                have.add(i["n"])
    return sorted(before, key=lambda i: i["n"]) + incs


class IncrementsFixture(unittest.TestCase):
    """BACKLOG.md has sections 0 and 1 (the normal case) and a range heading `## Increments 4 to 5`; increment 2 is
    known only from MILESTONES.md, 3 only from FEATURES.json (one row with the number as a string), 5 only from
    NEEDS-HUMAN.md, 4 from MILESTONES.md and FEATURES.json."""
    KNOWN = [0, 1, 2, 3, 4, 5]

    @classmethod
    def setUpClass(cls):
        cls.tmp, cls.root = copy_fixture("increments")
        cls.rc, cls.out, cls.page = render_fixture(cls.root)
        cls.snap = collect.snapshot(cls.root, collect.load_config(cls.root))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @staticmethod
    def problems(page, known):
        """What the owner could not see: a known increment without its fold, or the range heading without a banner."""
        folds = {int(d.attrs["id"][6:]) for d in page.all("details") if d.attrs.get("id", "").startswith("d-inc-")}
        out = [f"increment {n} has no fold" for n in known if n not in folds]
        banners = " ".join(h.text_all() for h in page.first("header", "hd").all("div", "hold"))
        if "## Increments 4 to 5" not in banners:
            out.append("no banner names the unreadable heading")
        return out

    def fold(self, n):
        return next(s for s in self.page.all("section", "inc") if s.first("details").attrs.get("id") == f"d-inc-{n}")

    def test_every_known_increment_renders_and_the_range_heading_warns(self):
        self.assertEqual(self.rc, 0)
        self.assertEqual(self.problems(self.page, self.KNOWN), [])
        order = [int(d.attrs["id"][6:]) for d in self.page.all("details") if d.attrs.get("id", "").startswith("d-inc-")]
        self.assertEqual(order, self.KNOWN)
        self.assertEqual(self.snap["backlog_unparsed"], ["## Increments 4 to 5"])
        banners = [h.text_all() for h in self.page.first("header", "hd").all("div", "hold")]
        self.assertTrue(any("without a BACKLOG.md section: 2, 3, 4, 5" in b for b in banners), banners)

    def test_negative_control_the_old_behaviour_fails(self):
        """The 0.8.3 dashboard (closed MILESTONES increments only, no heading check) fails the same test."""
        tmp, root = copy_fixture("increments")
        old_inc, old_unparsed = compute.increments, collect.backlog_unparsed
        compute.increments, collect.backlog_unparsed = legacy_increments, lambda text: []
        try:
            with tmp:
                _, _, page = render_fixture(root)
        finally:
            compute.increments, collect.backlog_unparsed = old_inc, old_unparsed
        self.assertEqual(self.problems(page, self.KNOWN), ["increment 2 has no fold", "increment 3 has no fold",
                                                           "increment 4 has no fold", "increment 5 has no fold",
                                                           "no banner names the unreadable heading"])

    def test_normal_sections_unchanged(self):
        cur = self.fold(1)
        self.assertIn("open", cur.first("details").attrs)
        self.assertEqual(len(cur.all("article", "slice")), 2)
        self.assertNotIn("no BACKLOG section", cur.text_all())
        self.assertIn("closed", self.fold(0).classes)

    def test_increment_known_only_from_milestones(self):
        inc = self.fold(2)
        self.assertIn("reports", inc.first("h3").text_all())
        self.assertIn("no BACKLOG section", inc.text_all())
        self.assertIn("a report of the last import prints", inc.first("p", "idesc").text_all())
        self.assertIsNotNone(inc.first("p", "uncut"), "slices not cut yet")
        self.assertIn("Known from MILESTONES.md", inc.text_all())

    def test_increment_known_only_from_features(self):
        inc = self.fold(3)
        self.assertIn("Increment 3", inc.first("h3").text_all())
        self.assertIn("ledger rows 1 / 2", inc.first("div", "barlbl").text_all(), "a string increment counts too")
        self.assertEqual([c.text for c in inc.first("ul", "rows").all("code")], ["R-003", "R-004"])
        self.assertIn("Known from FEATURES.json", inc.text_all())

    def test_increment_known_only_from_needs_human(self):
        inc = self.fold(5)
        self.assertIn("NH-02", inc.first("div", "acts").text_all())
        self.assertIn("Known from NEEDS-HUMAN.md", inc.text_all())

    def test_unsized_increments_are_shown_not_counted(self):
        incs = compute.increments(self.snap)
        self.assertEqual([i["n"] for i in compute.unsized(self.snap, incs)], [2, 3, 4, 5])
        per = compute.progress(self.snap, incs, 1)
        self.assertEqual([(n, t, d) for n, _, t, d in per], [(0, 1.0, 1.0), (1, 2.0, 0.25)])
        tile = self.page.first("div", "prog")
        self.assertIn("left out of the percentage, neither done nor remaining", tile.attrs["title"])
        self.assertIn("now: 2, 3, 4, 5", tile.attrs["title"])
        self.assertIn("42% of sized", tile.first("b").text_all())
        self.assertEqual(len(tile.all("span", "pun")), 4)
        self.assertIn("not sized yet: increments 2, 3, 4, 5, not counted", tile.text_all())

    def test_sized_projects_keep_the_plain_tile(self):
        tmp, root = copy_fixture("run")
        with tmp:
            _, _, page = render_fixture(root)
        self.assertNotIn("of sized", page.first("div", "prog").first("b").text_all())
        self.assertIsNone(page.first("span", "pun"))


class AgentCounters(unittest.TestCase):
    """Codex native worker logs carry the thread's cumulative usage (input includes cached) and no timestamps."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.run, self.outputs = self.root / "run", self.root / "outputs"
        self.run.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def native(self, stamp, end, inp, cached, out, thread="t-1", slice_id="slice-01-a"):
        d = self.outputs / "slices" / slice_id / "codex"
        d.mkdir(parents=True, exist_ok=True)
        base = d / f"slice-implementer-{stamp}-4242"
        lines = [{"type": "thread.started", "thread_id": thread}, {"type": "turn.started"},
                 {"type": "turn.completed", "usage": {"input_tokens": inp, "cached_input_tokens": cached, "output_tokens": out}}]
        base.with_suffix(".jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
        if end:
            base.with_suffix(".done").write_text(f"0 {end}\n")

    def recorded(self, *rows):
        with (self.run / "agent-usage-events.jsonl").open("a") as f:
            for session, alloc, inp, cached, out in rows:
                f.write(json.dumps({"runtime": "codex", "physical_source": "codex-rollout", "session_id": session,
                                    "turn_id": f"{alloc}/round-1", "timestamp": "2026-10-15T10:30:00Z",
                                    "role": "slice-implementer", "slice": "slice-01-a", "allocation": alloc,
                                    "usage": {"input_tokens": inp, "cached_input_tokens": cached, "output_tokens": out,
                                              "input_includes_cached": True}}) + "\n")

    def totals(self):
        events, coverage = collect.agent_usage(self.root, self.run, self.outputs)
        mine = [e for e in events if e["slice"] == "slice-01-a"]
        tok = None if any(e["tokens"] is None for e in mine) else sum(e["tokens"] for e in mine)
        act = None if any(e["active_s"] is None for e in mine) else sum(e["active_s"] for e in mine)
        return mine, tok, act, coverage

    def test_resumed_thread_counts_its_latest_cumulative_counter_and_every_run_time(self):
        self.native("20261015T100000Z", "2026-10-15T10:10:00Z", 1000, 900, 50)
        self.native("20261015T102000Z", "2026-10-15T10:25:00Z", 3000, 2600, 120)
        mine, tok, act, coverage = self.totals()
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["role"], "slice-implementer")
        self.assertEqual(tok, 3000 - 2600 + 120)
        self.assertNotEqual(tok, (1000 - 900 + 50) + (3000 - 2600 + 120))  # summing cumulative counters double-counts
        self.assertEqual(act, 15 * 60)
        self.assertNotIn("incomplete", coverage["detail"])

    def test_running_worker_leaves_time_unknown(self):
        self.native("20261015T100000Z", "2026-10-15T10:10:00Z", 1000, 900, 50)
        self.native("20261015T102000Z", None, 3000, 2600, 120)
        _, tok, act, coverage = self.totals()
        self.assertEqual(tok, 520)
        self.assertIsNone(act)
        self.assertIn("incomplete", coverage["detail"])

    def test_recorded_rows_keep_tokens_and_the_worker_supplies_time(self):
        self.native("20261015T100000Z", "2026-10-15T10:10:00Z", 3000, 2600, 120, thread="root")
        self.recorded(("root", "alloc-1", 3000, 2600, 120), ("child", "alloc-1", 500, 450, 10))
        mine, tok, act, _ = self.totals()
        self.assertEqual(tok, (400 + 120) + (50 + 10))
        self.assertEqual(act, 10 * 60)
        self.assertEqual(len(mine), 3)

    def test_recorded_rows_without_a_worker_log_stay_unknown_in_time(self):
        self.recorded(("root", "alloc-1", 3000, 2600, 120))
        _, tok, act, _ = self.totals()
        self.assertEqual(tok, 520)
        self.assertIsNone(act)


class Edges(unittest.TestCase):
    def test_unknown_state_is_visible(self):
        tmp, root = copy_fixture("run")
        with tmp:
            p = root / "docs/process/STATE.md"
            p.write_text(p.read_text().replace("| slice-06 | draft |", "| slice-06 | frobnicating |"))
            _, _, page = render_fixture(root)
            chips = [c for c in page.all("span", "chip unknown")]
            self.assertEqual(len(chips), 1)
            self.assertIn("frobnicating", chips[0].text)
            self.assertTrue(any("outside the vocabulary" in h.text_all() for h in page.all("div", "hold")))

    def test_inert_without_config(self):
        with tempfile.TemporaryDirectory() as d:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["--root", d]), 0)
            self.assertIn("nothing to do", buf.getvalue())
            self.assertEqual(list(pathlib.Path(d).iterdir()), [])

    def test_empty_state_dir_renders(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            (root / "s").mkdir()
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["--root", d, "--state-dir", str(root / "s"), "--now", NOW, "--no-history"]), 0)
            page = Tree((root / "s" / "dashboard.html").read_text()).root
            self.assertIsNotNone(page.first("div", "tiles"))

    def test_runs_as_a_directory_from_a_copy(self):
        """An installed copy runs as `python3 <dir>` under any parent directory."""
        tmp, root = copy_fixture("run")
        with tmp:
            dst = root / "scripts" / "sliceworks" / "dashboard"
            shutil.copytree(HERE.parent / "dashboard", dst, ignore=shutil.ignore_patterns("__pycache__"))
            r = subprocess.run([sys.executable, str(dst), "--root", str(root), "--now", NOW, "--no-history"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue((root / "docs/process/dashboard.html").exists())


if __name__ == "__main__":
    unittest.main()
