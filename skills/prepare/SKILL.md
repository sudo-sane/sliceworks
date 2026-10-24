---
name: prepare
description: Bring a project to the shape sliceworks reads from what it already has - import Spec Kit constitutions and specs, OpenSpec specs and changes, decision records, plans and roadmaps, architecture documents, end-to-end tests and boards into SPARK.md, INVARIANTS.md, DECISIONS.md, MILESTONES.md, SCENARIOS.json, FEATURES.json rows and BACKLOG.md slice candidates, each marked derived from its source and confirmed by the owner in one message; list the gaps that discover or design must fill. Use when the user says "prepare the project", "import our specs", "we already have ADRs / a roadmap / OpenSpec", "convert what we have", or when the dispatcher says prepare.
license: Apache-2.0
metadata:
  source: sudo-sane/sliceworks
  version: 0.5.1
---

# Prepare: import what exists

Method: `method/17-entry-and-intake.md` (the importers table). Inputs: `SURVEY.md` and the sources it lists.

Rules: propose, never replace; every derived line or row carries `derived from <path>`; ids are stable; the source document stays the project's own and is listed in `INDEX.md` as evidence; nothing is invented to fill a gap.

1. **Order the sources** from the survey: constitution and architecture first (invariants), then specs (scenarios and rows), then decision records and logs (D and Q entries), then plans and roadmaps (milestones and increments), then tests (criterion rows), then boards and issues (backlog and feedback).
2. **Import**, per source, with one explorer per large source:
   - Spec Kit: `.specify/memory/constitution.md` → `INVARIANTS.md` lines; `specs/<nnn>-<name>/spec.md` user stories and acceptance scenarios → `SCENARIOS.json` entries and `scenario` rows whose checks name the test that will prove them (`TODO: test name` when none exists); `plan.md` → `ARCHITECTURE.md` pointers; `tasks.md` → slice candidates in `BACKLOG.md`; `contracts/` → contract pins.
   - OpenSpec: `openspec/project.md` → `SPARK.md` and architecture pointers; `openspec/specs/<capability>/spec.md` requirements and their Given/When/Then scenarios → scenarios and rows; `openspec/changes/<id>/proposal.md`, `design.md`, `tasks.md` → an increment or slice per open change, decisions from proposals, thinning from `REMOVED` deltas.
   - Decision records and logs → `D` entries that link to the record; open items → `Q` entries with owners.
   - Plans and roadmaps → `MILESTONES.md` sections (promise, increments, exit criteria), each marked derived; and in `BACKLOG.md` one `## Increment <n>: <title>` section per increment (template `${CLAUDE_PLUGIN_ROOT}/templates/BACKLOG.md`), never a range heading such as `## Increments 2 to 5`, for every increment of `MILESTONES.md` and every increment number a `FEATURES.json` row or a `NEEDS-HUMAN.md` item uses. Each section carries `Exit demo:`, `Scenarios:` and `Human acts:` (the ids, or none) and, before the increment is sliced, a `Proposed slices (candidates): a; b; c.` line, even for increments far ahead; the dashboard and the design-doc lint read only this form.
   - Tests: end-to-end test names → `criterion` or `scenario` rows with must-run checks.
   - Boards and issues → `BACKLOG.md` slice candidates and `FEEDBACK.md` candidates.
3. **Validate**: every row has a check; every scenario names its milestone; schemas pass; the design-doc lint passes (its backlog check fails an increment without its own section and a heading it cannot read).
4. **Confirm**: one message to the owner with the counts per artifact, the five most consequential derivations, and the questions (one list). Apply confirmations; drop or mark `Q` what the owner declines.
5. **Gap list**: artifacts no source could seed, handed to `discover` (claims, riskiest assumptions) or `design` (scenarios, milestones, threat models). Run `start`.
