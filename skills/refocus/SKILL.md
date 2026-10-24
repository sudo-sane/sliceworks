---
name: refocus
description: Re-plan a sliceworks milestone mid-flight when a request or evidence changes the product - pause active slices at a safe point, record the pivot as a decision with the pivot marker and its evidence, audit every document, scenario, row, contract, spec and threat model against it with the two read-only analysts, archive what the new focus contradicts, re-derive increments and scenarios, re-run design for every amended surface, re-map rows without changing ids, mark paused slices with their resume increment, and leave a re-plan marker on the timeline. Use when the user says "refocus", "re-plan", "pivot", "the scope changed", "the product changed", "pause these slices", when intake answers pivot: yes, or when a Learn or Discover output invalidates the plan.
license: Apache-2.0
metadata:
  source: sudo-sane/sliceworks
  version: 0.6.1
---

# Refocus: re-plan a milestone

Method: `method/14-design-and-plan.md` (the trigger, the audit, archiving). Template: `refocus.md`. Output: `<state-dir>/refocus/<D-id>.md`, the archive directory, and the re-derived ledgers.

The trigger is not yours to guess: a change is a pivot when it alters the milestone promise, a riskiest assumption, an invariant, or a scenario of the current milestone (the business analysis says `Pivot: yes`); anything else is a feature and goes back to `intake` for placement.

1. **Pause.** Each active slice stops at a safe point: a candidate if T1 is green, otherwise a commit with a dated `PROGRESS.md` note. Set the slice `paused` with the reason.
2. **Record.** A `D` entry of class A2 or M with `· pivot` on its metadata line: what evidence changed the plan (round, metric, incident, owner statement), what is dropped, what is added, what moves to a later milestone. Veto window applies. Nothing below starts before this entry exists; the lint reads its date.
3. **Audit.** Spawn the `business-analyst` agent in audit mode with the D id, `SPARK.md`, `MILESTONES.md`, `SCENARIOS.json` and `FEATURES.json`; spawn the `system-analyst` agent in audit mode with the D id, `ARCHITECTURE.md`, `INVARIANTS.md`, the contracts, the specs, the threat models and `INDEX.md`. Both are read-only. Write `<state-dir>/refocus/<D-id>.md` from `${CLAUDE_PLUGIN_ROOT}/templates/refocus.md` with their verdict tables: one line per item, `keep`, `amend` or `archive`, the reason, the D. Every current document, every scenario and row of the milestone, every contract, spec and threat model appears once.
4. **Archive.** For each `archive` verdict: a document is moved with `git mv` to `<state-dir>/archive/<date>-<name>`, its `INDEX.md` row keeps its place with the archive path, status `archived (D-<n>)` and today as last reviewed; a spec gets `status: superseded by <name>` in place; a scenario becomes `thinned`; a row keeps its id with the D reference; a contract becomes `retired`. Record each in the Archived table. Archived files are never edited and never referenced by a brief or a contract (the lint fails on it).
5. **Re-derive.** Update `MILESTONES.md` (promise, increments and exit demos), `SCENARIOS.json` (milestone and increment of each scenario) and `BACKLOG.md` (slices per increment, one `## Increment <n>: <title>` section for every increment that remains, never a range heading). Row ids never change; thinned rows keep their ids and reference the D entry.
6. **Design.** Run the `design` skill for every design surface marked `amend` (`SPARK.md` for the promise, `INVARIANTS.md`, `ARCHITECTURE.md`, specs, threat models), each change citing the pivot D; refresh the last-reviewed date of every `INDEX.md` row marked `keep`. Run the design-doc lint: it fails while any current row predates the pivot or any brief references an archived file.
7. **Re-map.** Every `FEATURES.json` row gets its new `milestone` and `increment`; paused slices get the increment they resume in; contracts that no longer hold are `retired` or `amended` with a `CONTRACT` message to pinned slices; briefs of surviving slices are re-read for references to archived documents.
8. **Mark and resume.** Write the re-plan into `STATE.md` history and `PROGRESS.md`; the dashboard shows the marker on the timeline. Fill the Owner summary of the refocus file; the pivot D with its veto window is one of the owner notifications. Run `plan-increment` for the first re-planned increment; re-dispatch paused slices that survive from their branches with new allocations.
