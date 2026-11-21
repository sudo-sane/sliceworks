#!/usr/bin/env python3
# sliceworks 0.4.0. Project survey and phase dispatcher (method chapter 17).
#   survey.py --root <repo> [--json | --markdown] : what the project has, mapped to the phases' artifacts
#   survey.py --root <repo> --next                : the next skill to run and why (NEXT=<skill> REASON=<text>)
# Detection only; nothing is written. Standard library only.
import argparse, json, os, pathlib, re, sys

PHASE_ARTIFACTS = {  # phase -> (artifact label, relative path under the state dir, or absolute marker)
    "spark": [("SPARK.md", "SPARK.md")],
    "discover": [("rounds", "rounds")],
    "decide": [("DECISIONS.md", "DECISIONS.md")],
    "design": [("INVARIANTS.md", "INVARIANTS.md"), ("ARCHITECTURE.md", "ARCHITECTURE.md"), ("SCENARIOS.json", "SCENARIOS.json"), ("MILESTONES.md", "MILESTONES.md")],
    "plan": [("BACKLOG.md", "BACKLOG.md"), ("FEATURES.json", "FEATURES.json"), ("slices", "slices")],
    "build": [("STATE.md", "STATE.md"), ("PROGRESS.md", "PROGRESS.md")],
    "accept": [("accept", "accept")],
    "release": [("release checklists", "releases")],
    "operate": [("INCIDENTS.md", "INCIDENTS.md")],
    "learn": [("FEEDBACK.md", "FEEDBACK.md"), ("evals", "../evals")],
}


def exists(root, rel):
    return (root / rel).exists()


def read_config(root):
    cfg = {}
    p = root / ".sliceworks" / "config.env"
    if not p.exists():
        return None
    for line in p.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        m = re.match(r"^([A-Z_][A-Z0-9_]*)=(.*)$", line)
        if m:
            cfg[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return cfg


def detect_stack(root):
    stack = {"languages": [], "manifests": [], "commands": {}}
    checks = {"go.mod": "go", "package.json": "javascript", "pyproject.toml": "python", "requirements.txt": "python", "Cargo.toml": "rust", "pom.xml": "java", "build.gradle": "java", "Gemfile": "ruby", "composer.json": "php", "Package.swift": "swift", "mix.exs": "elixir"}
    for f, lang in checks.items():
        if exists(root, f):
            stack["manifests"].append(f)
            if lang not in stack["languages"]:
                stack["languages"].append(lang)
    mk = root / "Makefile"
    if mk.exists():
        targets = re.findall(r"^([a-zA-Z0-9_-]+):", mk.read_text(), re.M)
        stack["commands"]["make"] = sorted(set(targets))[:40]
    pj = root / "package.json"
    if pj.exists():
        try:
            stack["commands"]["npm"] = sorted(json.loads(pj.read_text()).get("scripts", {}).keys())
        except Exception:
            pass
    ci = [str(p.relative_to(root)) for p in list(root.glob(".github/workflows/*.y*ml")) + list(root.glob(".gitlab-ci.yml")) + list(root.glob(".circleci/config.yml"))]
    stack["ci"] = ci
    # Walk once with pruning: worktree copies, dependency trees and build output would make a repository
    # survey take minutes and count other checkouts' tests as this project's.
    prune = {".git", "node_modules", ".claude", ".worktrees", "vendor", "build", "dist", "target", "outputs", ".venv", "venv", "__pycache__", ".next", ".cache", "coverage"}
    test_re = re.compile(r"(_test\.go|^test_.*\.py|_test\.py|\.test\.[tj]sx?|\.spec\.[tj]sx?|_test\.rs)$")
    tests, e2e, seen = [], [], 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [x for x in dirnames if x not in prune and not x.startswith(".")]
        for fn in filenames:
            seen += 1
            if seen > 200000:
                dirnames[:] = []
                break
            if test_re.search(fn):
                p = pathlib.Path(dirpath) / fn
                tests.append(p)
                if fn.endswith(".go") and len(e2e) < 200:
                    try:
                        e2e += re.findall(r"func (TestAC\d+\w*|Test\w*E2E\w*|Test\w*Journey\w*)\(", p.read_text(errors="ignore"))
                    except Exception:
                        pass
    stack["test_files"] = len(tests)
    stack["e2e_test_names"] = sorted(set(e2e))[:50]
    return stack


def detect_process_systems(root):
    s = {}
    s["spec_kit"] = {"present": exists(root, ".specify"), "constitution": exists(root, ".specify/memory/constitution.md"),
                     "features": sorted(str(p.relative_to(root)) for p in root.glob("specs/[0-9][0-9][0-9]-*/spec.md"))}
    s["openspec"] = {"present": exists(root, "openspec"), "project": exists(root, "openspec/project.md"),
                     "specs": sorted(str(p.relative_to(root)) for p in root.glob("openspec/specs/*/spec.md")),
                     "changes": sorted(p.name for p in root.glob("openspec/changes/*") if p.is_dir() and p.name != "archive")}
    adr_dirs = [d for d in ("docs/adr", "docs/adrs", "docs/decisions", "adr", "doc/adr") if (root / d).is_dir()]
    s["adr"] = {"dirs": adr_dirs, "count": sum(len(list((root / d).glob("*.md"))) for d in adr_dirs)}
    s["decisions_log"] = [str(p.relative_to(root)) for p in root.glob("docs/decisions.md")]
    s["kanban_md"] = {"present": exists(root, "kanban/tasks") or exists(root, "kanban")}
    s["plans"] = sorted(str(p.relative_to(root)) for p in list(root.glob("docs/plans/*.md")) + list(root.glob("docs/roadmap*.md")) + list(root.glob("ROADMAP.md")))[:30]
    s["runbooks"] = exists(root, "docs/runbooks")
    s["postmortems"] = exists(root, "docs/postmortems")
    arch, seen_arch = [], set()
    for f in ("ARCHITECTURE.md", "docs/architecture.md", "docs/ARCHITECTURE.md"):
        if exists(root, f):
            key = os.path.realpath(root / f).lower()  # case-insensitive file systems report both spellings
            if key not in seen_arch:
                seen_arch.add(key); arch.append(f)
    s["architecture_doc"] = arch
    s["readme"] = exists(root, "README.md")
    s["changelog"] = exists(root, "CHANGELOG.md")
    return s


LIBRARY = "sudo-sane/engineering-skills"
LIBRARY_SOURCES = (LIBRARY, "glotyuids/engineering-skills")  # the owner's former account name stamps copies installed before the rename
LIBRARY_PACKS = {  # pack -> skills, as the library's manifest lists them (kept in sync by hand; the library is the source)
    "core": ["bootstrap-project"],
    "process": ["git-workflow", "documentation-standards", "deslop", "review-plan", "integration-testing", "incident-response", "kanban-md", "security-guidelines"],
    "infra": ["cicd-build-deploy", "terraform-conventions", "ansible-deploy", "kubernetes-helm", "makefile-conventions", "secrets-management"],
    "cloud-yandex": ["yandex-cloud"],
    "go": ["go-conventions", "new-microservice", "api-and-events", "observability-and-quality"],
    "database": ["postgres-patterns", "database-migrations"],
    "frontend": ["react-conventions", "design-system-authoring", "i18n-conventions", "ui-test-playwright"],
    "llm": ["llm-pipeline-rules", "mcp-server-authoring", "skill-authoring"],
    "writing": ["purposeful-text-writing", "writing-honesty-gates", "cover-letter-craft", "review-cover-letter"],
    "lang-ru": ["ru-ui-strings", "ru-en-tone-transfer", "ru-market-job-application-norms", "bilingual-product-architecture"],
}
PHASE_USES = {  # phase -> library skills the sliceworks phase skills call when present
    "adopt": ["bootstrap-project"], "design": ["review-plan", "documentation-standards"], "plan": ["kanban-md"],
    "build": ["git-workflow", "integration-testing", "security-guidelines"], "release": ["cicd-build-deploy", "secrets-management", "documentation-standards"],
    "operate": ["incident-response", "documentation-standards"], "learn": ["deslop"],
}


def detect_library_skills(root):
    """Skills installed from the engineering-skills library, by name, with version and where they live."""
    found = {}
    for base in (".claude/skills", ".agents/skills", ".cursor/skills"):
        for sk in root.glob(f"{base}/*/SKILL.md"):
            try:
                head = sk.read_text(errors="ignore")[:4000]
            except Exception:
                continue
            if not head.startswith("---"):
                continue
            fm = head.split("---", 2)[1]
            if not any(f"source: {s}" in fm for s in LIBRARY_SOURCES):
                continue
            m = re.search(r"^\s*version:\s*(\S+)", fm, re.M)
            name = sk.parent.name
            found.setdefault(name, {"version": m.group(1) if m else None, "locations": []})["locations"].append(base)
    packs = {}
    for pack, skills in LIBRARY_PACKS.items():
        have = [s for s in skills if s in found]
        if have:
            packs[pack] = {"installed": have, "missing": [s for s in skills if s not in found]}
    return {"skills": found, "packs": packs}


def recommend_packs(stack, library, phases):
    """Packs worth installing for this stack and these phases, minus the ones already (partly) installed."""
    want = {"core", "process"}
    langs = set(stack.get("languages", []))
    if "go" in langs: want.add("go")
    if "javascript" in langs: want.add("frontend")
    if {"release", "operate"} & set(phases): want.add("infra")
    manifests = set(stack.get("manifests", []))
    if "go.mod" in manifests or "pyproject.toml" in manifests: want.add("database")
    return sorted(w for w in want if w not in library["packs"])


def library_uses(library):
    """Per phase: which of the library skills the phase skills would call are present, and which are absent."""
    out = {}
    for phase, skills in PHASE_USES.items():
        out[phase] = {"present": [s for s in skills if s in library["skills"]], "absent": [s for s in skills if s not in library["skills"]]}
    return out


def detect_agent_config(root):
    slug = str(root).replace(os.sep, "-")
    mem = pathlib.Path.home() / ".claude" / "projects" / slug / "memory" / "MEMORY.md"
    settings = root / ".claude" / "settings.json"
    hooks = False
    plugins = []
    if settings.exists():
        try:
            d = json.loads(settings.read_text())
            hooks = bool(d.get("hooks"))
            plugins = sorted(k for k, v in d.get("enabledPlugins", {}).items() if v)
        except Exception:
            pass
    return {
        "claude_md": exists(root, "CLAUDE.md") or exists(root, ".claude/CLAUDE.md"),
        "agents_md": exists(root, "AGENTS.md"),
        "claude_rules": sorted(str(p.relative_to(root)) for p in root.glob(".claude/rules/*.md")),
        "claude_agents": sorted(p.stem for p in root.glob(".claude/agents/*.md")),
        "claude_skills": sorted(p.name for p in root.glob(".claude/skills/*") if p.is_dir()),
        "agents_skills": sorted(p.name for p in root.glob(".agents/skills/*") if p.is_dir()),
        "cursor": exists(root, ".cursor"), "codex": exists(root, ".codex"), "copilot": exists(root, ".github/copilot-instructions.md"),
        "settings_hooks": hooks, "enabled_plugins": plugins, "mcp": exists(root, ".mcp.json"),
        "memory": str(mem) if mem.exists() else None,
        "worktrees": len([p for p in root.glob(".claude/worktrees/*") if p.is_dir()]),
    }


def phase_coverage(root, cfg):
    state = pathlib.Path(cfg.get("SW_STATE_DIR", "docs/process")) if cfg else None
    cov = {}
    for phase, items in PHASE_ARTIFACTS.items():
        have, missing = [], []
        for label, rel in items:
            p = (root / state / rel) if state is not None else None
            ok = p is not None and p.exists() and (p.stat().st_size > 0 if p.is_file() else any(p.iterdir()))
            if ok and rel == "FEATURES.json":
                try:
                    ok = len(json.loads(p.read_text())) > 0
                except Exception:
                    ok = False
            if ok and rel == "SCENARIOS.json":
                try:
                    ok = len(json.loads(p.read_text())) > 0
                except Exception:
                    ok = False
            (have if ok else missing).append(label)
        cov[phase] = {"have": have, "missing": missing, "status": "have" if not missing else ("partial" if have else "missing")}
    return cov


def ledger_summary(root, cfg):
    if not cfg:
        return {}
    state = root / cfg.get("SW_STATE_DIR", "docs/process")
    out = {"rows": 0, "passing": 0, "kinds": {}, "briefs": 0, "active_slices": 0, "ready_slices": 0, "milestone_state": None}
    f = state / "FEATURES.json"
    if f.exists():
        try:
            rows = json.loads(f.read_text())
            out["rows"] = len(rows); out["passing"] = sum(1 for r in rows if r.get("passes"))
            for r in rows:
                k = r.get("kind", "scenario"); out["kinds"][k] = out["kinds"].get(k, 0) + 1
        except Exception:
            out["rows_error"] = True
    out["briefs"] = len(list((state / "slices").glob("slice-*.md"))) if (state / "slices").is_dir() else 0
    st = state / "STATE.md"
    if st.exists():
        text = st.read_text()
        out["active_slices"] = len(re.findall(r"^\| slice-[^|]*\| (active|repair|review)", text, re.M))
        out["ready_slices"] = len(re.findall(r"^\| slice-[^|]*\| ready", text, re.M))
        m = re.search(r"^## Milestone\n(?:.*\n)*?state: *(\S+)", text, re.M)
        out["milestone_state"] = m.group(1) if m else None
    return out


def decide_next(root, cfg, cov, ledger, systems, agent_cfg, survey_fresh):
    if cfg is None:
        return "adopt", "no .sliceworks/config.env: the project has not adopted the method"
    if not survey_fresh:
        return "survey", "no SURVEY.md in the state directory, or it is older than the configuration"
    importable = bool(systems["spec_kit"]["features"] or systems["openspec"]["specs"] or systems["adr"]["count"] or systems["plans"] or systems["architecture_doc"])
    design_missing = cov["design"]["status"] != "have"
    if importable and design_missing and cov["spark"]["status"] == "missing":
        return "prepare", "existing specifications, decisions or plans can seed the design artifacts before anything is written from scratch"
    if cov["spark"]["status"] == "missing" and ledger["rows"] == 0:
        return "discover", "no SPARK.md and no rows: the project starts from an idea; open the first round"
    if cov["design"]["status"] != "have":
        return "design", "scenarios or milestones are missing: generate them before planning"
    if ledger["rows"] == 0:
        return "design", "scenarios exist but no ledger rows: derive rows with checks"
    if ledger["briefs"] == 0 and ledger["active_slices"] == 0:
        return "plan-increment", "rows exist but no brief: plan the first increment"
    if ledger["passing"] == ledger["rows"] and ledger["rows"] > 0:
        return "accept", "every row passes: prepare the acceptance packet"
    return "resume", f"{ledger['active_slices']} active and {ledger['ready_slices']} ready slices: continue the run"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--next", action="store_true")
    a = ap.parse_args(argv)
    root = pathlib.Path(a.root).resolve()
    cfg = read_config(root)
    stack = detect_stack(root); systems = detect_process_systems(root); agent_cfg = detect_agent_config(root)
    cov = phase_coverage(root, cfg); ledger = ledger_summary(root, cfg)
    library = detect_library_skills(root)
    phases = ((cfg or {}).get("SW_PHASES") or "spark discover decide design plan build accept release operate learn").split()
    library["recommended_packs"] = recommend_packs(stack, library, phases); library["phase_uses"] = library_uses(library)
    survey_fresh = False
    if cfg:
        sp = root / cfg.get("SW_STATE_DIR", "docs/process") / "SURVEY.md"
        survey_fresh = sp.exists() and sp.stat().st_mtime >= (root / ".sliceworks" / "config.env").stat().st_mtime
    nxt, reason = decide_next(root, cfg, cov, ledger, systems, agent_cfg, survey_fresh)
    report = {"root": str(root), "adopted": cfg is not None, "profile": (cfg or {}).get("SW_PROFILE"), "stack": stack, "process_systems": systems, "agent_config": agent_cfg, "library": library, "phase_coverage": cov, "ledger": ledger, "next": {"skill": nxt, "reason": reason}}
    if a.next:
        print(f"NEXT={nxt} REASON={reason}")
        return 0
    if a.json or not a.markdown:
        print(json.dumps(report, indent=2))
        return 0
    lines = [f"# Survey of {root.name}", "",
             f"Adopted: {'yes, profile ' + str(report['profile']) if cfg else 'no'}. Next: **{nxt}** ({reason}).", "",
             "## Stack",
             f"- languages: {', '.join(stack['languages']) or 'none detected'}; manifests: {', '.join(stack['manifests']) or 'none'}",
             ("- commands: " + "; ".join(f"{k}: {', '.join(v[:12])}" for k, v in stack['commands'].items())) if stack['commands'] else "- commands: none detected",
             f"- CI: {', '.join(stack['ci']) or 'none'}; test files: {stack['test_files']}; end-to-end tests named: {len(stack['e2e_test_names'])}", "",
             "## Skills library (engineering-skills)",
             f"- installed skills: {len(library['skills'])} in packs {', '.join(library['packs']) or 'none'}",
             f"- recommended packs to add: {', '.join(library['recommended_packs']) or 'none'}",
             "- phase bindings: " + "; ".join(f"{ph}: {', '.join(u['present']) or 'none'} (absent: {', '.join(u['absent']) or 'none'})" for ph, u in library['phase_uses'].items()), "",
             "## Process systems"]
    sk = systems["spec_kit"]; osp = systems["openspec"]
    lines += ["", "## Skills library (engineering-skills)", f"- installed skills: {len(library['skills'])} in packs {', '.join(library['packs']) or 'none'}", f"- recommended packs to add: {', '.join(library['recommended_packs']) or 'none'}", "- phase bindings: " + "; ".join(f"{ph}: {', '.join(u['present']) or 'none'} (absent: {', '.join(u['absent']) or 'none'})" for ph, u in library['phase_uses'].items())]
    lines += ["", "## Process systems"]
    lines += [f"- Spec Kit: {'present' if sk['present'] else 'absent'}; constitution: {sk['constitution']}; features: {len(sk['features'])}", f"- OpenSpec: {'present' if osp['present'] else 'absent'}; specs: {len(osp['specs'])}; open changes: {len(osp['changes'])}", f"- ADRs: {systems['adr']['count']} in {', '.join(systems['adr']['dirs']) or 'no directory'}; decisions log: {', '.join(systems['decisions_log']) or 'none'}", f"- plans or roadmaps: {len(systems['plans'])}; architecture document: {', '.join(systems['architecture_doc']) or 'none'}; kanban-md: {systems['kanban_md']['present']}; runbooks: {systems['runbooks']}", "", "## Agent configuration", f"- CLAUDE.md: {agent_cfg['claude_md']}; AGENTS.md: {agent_cfg['agents_md']}; rules: {len(agent_cfg['claude_rules'])}; agents: {len(agent_cfg['claude_agents'])}; skills: {len(agent_cfg['claude_skills'])} (.claude) + {len(agent_cfg['agents_skills'])} (.agents)", f"- hooks in settings: {agent_cfg['settings_hooks']}; plugins: {', '.join(agent_cfg['enabled_plugins']) or 'none'}; MCP: {agent_cfg['mcp']}; memory: {agent_cfg['memory'] or 'none'}; worktrees: {agent_cfg['worktrees']}", "", "## Phase coverage", "| phase | status | have | missing |", "|---|---|---|---|"]
    for ph, c in cov.items():
        lines.append(f"| {ph} | {c['status']} | {', '.join(c['have']) or ''} | {', '.join(c['missing']) or ''} |")
    if ledger:
        lines += ["", "## Ledger", f"- rows: {ledger['rows']} ({ledger['passing']} passing); kinds: {ledger['kinds']}; briefs: {ledger['briefs']}; active slices: {ledger['active_slices']}; ready: {ledger['ready_slices']}; milestone state: {ledger['milestone_state']}"]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
