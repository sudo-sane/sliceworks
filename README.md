# sliceworks

An autonomous development life cycle for AI coding agents.

One long-lived **coordinator** session keeps a small set of state files, freezes contracts, writes
briefs and dispatches **slice implementers** into their own git worktrees. Deterministic
**verification tiers** decide what is reviewable; an independent **reviewer** reads the diff in a
fresh context; the coordinator merges by SHA and runs the merge gate in the background. Progress
is the number of acceptance scenarios passing end to end on the integration branch, recorded in a
**feature ledger** with pass flags and evidence. A human is interrupted only for acts a machine may
not perform: credentials, money, legal and consent, real personal data, irreversible actions outside
the repository. Everything else runs under recorded, vetoable defaults, within **budget holds** on
the provider's usage window, behind a **kill switch** file.

The method was extracted from a real run and is written so that every component names the failure
it prevents; a component whose failure stops occurring is removed at the retrospective.

**Codex security update:** versions 0.8.0 and 0.8.1 exposed the whole main `.git` directory to writers. Adopters must take **0.8.2** before using writer roots; see the [Git boundary and live probe](scripts/runtimes/codex/README.md#git-metadata-boundary-082).

## Install

### Claude Code

From the terminal, once per machine (in the desktop app the `/plugin` slash form opens the plugin panel instead of running the subcommand, so use the CLI):

```bash
claude plugin marketplace add sudo-sane/engineering-skills
```

```bash
claude plugin install sliceworks@engineering-skills --scope user
```

Then, in a session in the project you want to run this way, `/sliceworks:start`. Use `--scope project` to commit the install into the project's `.claude/settings.json` so teammates are prompted for it.

Local development or a checkout of this repository:

```bash
claude --plugin-dir /path/to/sliceworks
```

### Update (Claude Code)

A release bumps the version in the plugin manifest; your install stays on the cached version until it is updated. One command:

```bash
claude plugin update sliceworks@engineering-skills
```

Then `/reload-plugins` or a new session. To make it automatic, mark the marketplace in `~/.claude/settings.json`; Claude Code then checks after the first message of a session and installs new versions on its own:

```json
"extraKnownMarketplaces": {
  "engineering-skills": { "source": { "source": "github", "repo": "sudo-sane/engineering-skills" }, "autoUpdate": true }
}
```

If the library's marketplace file itself changed (a new entry, a new source), refresh it first with `claude plugin marketplace update engineering-skills`. Maintainers release with `scripts/release.sh <version>` (tests, validation, commit, tag, push, and the marketplace entry).

### Codex

Codex reads the same `AGENTS.md` and loads skills from `.agents/skills` (project) or `~/.agents/skills` (user). Two ways in.

**As a Codex plugin.** This repository carries `.agents/plugins/marketplace.json`, the file Codex reads for a marketplace, and `.codex-plugin/plugin.json`, the Codex manifest (same name and version as the Claude Code one). Add to `~/.codex/config.toml` (or the project's `.codex/config.toml`):

```toml
[marketplaces.sliceworks]
source_type = "git"
source = "https://github.com/sudo-sane/sliceworks.git"

[plugins."sliceworks@sliceworks"]
enabled = true
```

Then restart Codex and trust the plugin's hooks (`/hooks`); the skills appear as `sliceworks` skills and the guards run on Codex's tool calls. Launcher behavior is covered with a stand-in `codex`; the adapter records the installed CLI checks and their limitations.

**By copy.** From a clone, into a project:

```bash
git clone https://github.com/sudo-sane/sliceworks
sliceworks/scripts/install.sh /path/to/project --tools codex --hooks
```

(`--hooks` writes `.codex/hooks.json` running the clone's hooks; use a single source of enforcement), or for every project, user scope:

```bash
sliceworks/scripts/install.sh --user --tools codex
```

The script copies the skills and generates the role agents into `.codex/agents`, never symlinks, never overwrites (`--force` to replace), and keeps the provenance stamps the `update` skill compares. `--tools codex,claude` also installs the agents into `.claude/agents` for a Claude Code setup without the plugin; `--tools cursor` targets `.cursor`.

**A project-local copy with its own hooks.** Set `SW_PLUGIN_HOOKS=off` in the project's `.sliceworks/config.env`: the package's kill switch, budget, money, role and both Stop hooks exit silently, while session context may still print. Keep the project's own enforcement hooks enabled. In the project's `.claude/settings.json`, merge `"enabledPlugins": {"sliceworks@engineering-skills": false}` (use the actual installed marketplace name); disable the Codex plugin in that project's `.codex/config.toml` too if Codex loads it. Disabling plugin loading also removes duplicate skill names. A copy install whose only hooks call the package's hook bodies must leave `SW_PLUGIN_HOOKS=on`; setting it off would disable its only enforcement. See the [Codex adapter](scripts/runtimes/codex/README.md) for the exact migration steps.

Writers have no network access. Set `SW_CODEX_BIN` to the CLI executable if `codex` is absent from PATH; a host-side request runner brokers database gates without a coordinator model turn. Configure `SW_PREHANDOFF_CMD` to run lint and every database-free test for changed packages before HOLD or CANDIDATE. Project verifiers must honor the writable metric paths the dispatcher exports, and the coordinator imports those rows with `collect.py --merge-worker-metrics`. The adapter documents the request protocol and verifier contract.

**What Codex gets today.** The twenty skills and the method, templates and schemas they read; the same hooks (kill switch, budget and money guards, role guard, the T0 stop gate); the role agents generated as `.codex/agents/*.toml` with a parity check; implementers and reviewers as separate `codex exec` worker processes in their own worktrees and sandboxes (`scripts/runtimes/codex/dispatch.sh`, `status.sh`); and a Stop hook that keeps the coordinator going while workers run. The Codex adapter, [`scripts/runtimes/codex/README.md`](scripts/runtimes/codex/README.md), maps each Claude Code mechanism the skills name to its Codex counterpart and lists the known limits. To update a copy install, re-run `install.sh` with `--force`, or run the `update` skill, which replaces stale copies and keeps hand-edited ones.

### Other runtimes

Cursor, Copilot and Gemini read the Agent Skills format too: `scripts/install.sh /path/to/project --tools cursor` (or `copilot`, `gemini`) copies the skills into the directory each one reads, and `--user` installs them for every project.

## The life cycle

A product moves through named **milestones** (MVP is one name among others). Each milestone has ten phases: Spark, Discover, Decide, Design, Plan, Build, Accept, Release, Operate, Learn. Build is the autonomous run described above; the other phases have their own ledgers, checks and skills, and the owner's time concentrates in Decide, Accept and Release. One ledger holds every phase's rows, each with a `kind` that says what its check proves. See `method/00-lifecycle.md`.

## Starting

`/sliceworks:start` looks at the project and runs what is next. A blank repository is adopted; a newly adopted one is surveyed (stack, commands, the specifications, decisions, plans and boards it already has, its agent configuration); a project with existing specifications or decision records has them imported before anything is written from scratch; an idea opens a research round; scenarios without rows go to design; rows without a brief go to increment planning; a running project resumes; a finished milestone goes to acceptance. A request typed in chat ("add a feature", "users asked for") goes through `intake`: business analysis, system analysis, scenario adaptation, decisions, placement. See `method/17-entry-and-intake.md`. A request that changes the milestone promise, a riskiest assumption, an invariant or a scenario of the current milestone is a pivot, not a feature: `refocus` pauses the slices, records the decision, audits every document, scenario, row, contract and spec against it, archives what the new focus contradicts, re-runs the design and re-plans. See `method/14-design-and-plan.md`.

## Completion is read, not received

A worker may be a subagent whose completion is delivered, or a native chat plus a CLI session plus a long test with three lifetimes. The method does not depend on the difference: every dispatch is an **allocation record** (worker, worktree, branch, full base commit, allowed paths, completion condition), every worker ends by committing a **handoff** on its branch, and the **collector** reads completion from process handles, tier logs, branch heads and handoffs. No acknowledgement or status request is ever a prerequisite; a message to a worker counts as a dispatch for the budget. See `method/19-allocation-and-completion.md`.

## The dashboard

Every adopted project gets the same page: the first run's dashboard, generated by the package from the state files and rebuilt every 30 seconds by `scripts/sliceworks/dashboard-loop.sh` with no model turn. Tiles for backlog progress, the current milestone's scenarios, the weekly budget and money; holds as banners; one fold per increment with its slices as cards with a stepper, a timeline and the human acts that block it; the owner's inbox, veto clocks, open questions and milestones underneath. One self-contained HTML file, light and dark, no network. `adopt` installs it (`scripts/install.sh <project> --dashboard`); run it by hand with `python3 scripts/sliceworks/dashboard --root .`. See `method/09-metrics-and-improvement.md`.

## With the skills library

`sliceworks` owns the life cycle; [`engineering-skills`](https://github.com/sudo-sane/engineering-skills) owns how each engineering thing is done. The survey detects which packs a project has, recommends the rest for its stack, and each phase names the library skill it calls (`review-plan` at design, `incident-response` at operate, the infra pack at release) and what happens when it is absent. See `method/18-skills-library.md`.

## Profiles

| Profile | For | What runs |
|---|---|---|
| `lite` | one developer, one session | state files, tiers, briefs, kill switch, dashboard; the session is coordinator and implementer at once; the Stop hook is the only gate |
| `full` | unattended runs | coordinator plus worktree-isolated implementers, reviewers, named-risk review, budget holds, stall and ready detection |
| `dual` | Claude Code and Codex on one project | `full` plus the generated Codex agent files, the hook shim and the parity check |

## Read

- `method/` is the process: principles, roles, lifecycles, preparation, verification, review and
  integration, communication, budget, metrics and the improvement loop, autonomous operation,
  the component table, the glossary.
- `rationale/` is why: the research findings behind the rules, the lessons from the first run,
  the sources.
- `docs/design/2026-10-12-extraction-analysis.md` is the design note this package was built from.

## Status

0.8.7: allocation records, handoffs and the collector; Codex install paths and the copy installer; bound to the skills library, with a design procedure in the architect; the method book covers the whole life cycle and the entry sequence; the manifest, ten agents, hooks with a money guard, twenty skills, templates and schemas validate; the dashboard generator renders every adopted project's page; the survey script, the hook tests, the lint tests, the survey tests and the dashboard tests pass. The verification harness and the Python library follow (`docs/design/2026-10-12-extraction-analysis.md`, section 10; `docs/design/2026-10-12-lifecycle-coverage.md`, section 8).

## Licence

Apache-2.0.
