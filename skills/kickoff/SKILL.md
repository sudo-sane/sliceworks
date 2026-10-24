---
name: kickoff
description: Run the one kickoff session of a sliceworks run with the owner - scope in and out, the human-only list for this product, increments with exit demos, acceptance scenarios as feature-ledger rows with checks, the first contracts, the budget share and model routing, and the kickoff decisions recorded with veto windows. Use when the user says "kick off the run", "plan the increments", "turn this scope into feature rows", "start the autonomous run", or after adopt in a project with no backlog yet.
license: Apache-2.0
metadata:
  source: sudo-sane/sliceworks
  version: 0.5.1
---

# Kickoff

This is the one session in which the owner answers questions in chat; it is the Decide-to-Plan boundary of the first milestone for a project that starts with a known scope (method chapter 0). It composes `discover` (light: one round on the riskiest assumptions), `decide`, `design` and `plan-increment`. Everything after it runs under recorded defaults. Read `method/00-lifecycle.md`, `method/03-lifecycles.md` and `method/04-preparation.md` first.

1. **Scope.** State what is in and what is out, as a short list each. A new product question with no recommended default becomes a human-only item, not a guess.
2. **Human-only list.** Start from method 10 and add the product's own acts (paid runs above a cap, real users, real data, publications, signatures). Record additions in `.sliceworks/config.env` and `NEEDS-HUMAN.md`.
3. **Milestone and increments.** Name the first milestone in `MILESTONES.md` (promise, success metrics, exit criteria, gate families). Three to six increments, each with an exit demo a script can run on synthetic data, ordered so the first is a walking skeleton. User scenarios into `SCENARIOS.json`. Write `BACKLOG.md` from the template: one `## Increment <n>: <title>` section per increment (template `${CLAUDE_PLUGIN_ROOT}/templates/BACKLOG.md`), never a range heading such as `## Increments 2 to 5`, each with exit demo, scenarios and human acts, then a slice table (`slice | state | content | depends on | writer`) for the increments sliced today and a `Proposed slices (candidates): a; b; c.` line for the later ones.
4. **Feature ledger.** One row per acceptance scenario and per slice criterion in `FEATURES.json` (schema in `${CLAUDE_PLUGIN_ROOT}/schemas/features-row.schema.json`): `id`, `increment`, `slice`, `title`, `cwd`, `check` (a command that fails unless the named test ran and passed), `passes: false`, `evidence: null`, `human_act`, `tasks`. A row without a runnable check is not a row.
5. **Contracts.** For the first slices, run the `contract-author` agent; record class B choices in `STATE.md` Decisions; freeze with fixtures; record file and SHA under Contracts.
6. **Budget and models.** The run's share of the window and the holds (already in `config.env`); model routing by role (method 8); the writer cap.
7. **Decisions.** Every default applied today is a `D` entry in `DECISIONS.md` with class, applied default, consequence of reversing, veto-by date and status `defaulted`; every open question a `Q` entry with owner and due date.
8. **Briefs.** Write the first ready brief per writer with the `brief` skill. Move increment 0 to `started` in `STATE.md`.
9. **Hand over.** Tell the owner what they will see (dashboard, status, four notifications), how to stop (the STOP file) and how to resume (`resume`). Then the coordinator runs.
