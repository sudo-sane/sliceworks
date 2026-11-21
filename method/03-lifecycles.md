# 3. Lifecycles

## Product and milestone

A product moves through named milestones (chapter 0); each milestone's Build phase is a sequence of increments, each ending in an automated demo run and a retrospective. Full-suite checkpoints inside a milestone are recorded `MILESTONE_GREEN` when T3 passes. The autonomous run ends at the milestone's **engineering-complete** state: every ledger row of the milestone that does not require a human-only act is `passes: true`, every row that does is `blocked_on_human` with its exact ask in the inbox. Acceptance, release and operation follow as chapters 15 and 16.

## Increment

| State | Entry condition | Owner |
|---|---|---|
| `planned` | listed in `BACKLOG.md` with slices and scenarios | coordinator |
| `started` | class A2 defaults for the increment recorded with veto dates; contracts for the first slices frozen; at least one ready brief per writer; any human-only act listed in the inbox | coordinator |
| `running` | slices in flight | coordinator |
| `demo` | every slice merged and green; the demo runner has produced the demo artifact with every exit scenario passing | coordinator |
| `retro` | efficiency review read; at most three changes adopted; harness pruned; retrospective written | coordinator with the efficiency reviewer |
| `closed` | milestones recorded; owner notified with the demo and retro links; next increment `started` | coordinator |

A demo run that fails more than one scenario holds the next increment until the retrospective names the cause. The owner's veto window for an increment's defaults is 48 hours from the `started` notification; a veto reopens the affected slices only.

## Slice

| State | Meaning | Moves it |
|---|---|---|
| `proposed` | listed in the backlog | coordinator |
| `ready` | Definition of Ready passed; brief written | coordinator |
| `active` | implementer dispatched with the brief and the goal condition | coordinator |
| `candidate` | T1 green at that SHA; under candidate cadence the collector confirms the exact committed handoff | implementer / collector |
| `in_review` | reviewer spawned | coordinator |
| `repair` | findings sent; implementer resumed | implementer |
| `merged` | merged by SHA; T2 running | coordinator |
| `green` | T2 passed | coordinator |
| `accepted` | ledger rows flipped with evidence; implementer re-dispatched or released | coordinator |
| `waiting` | deliberately waits on another slice; skipped by the stall check | coordinator |
| `blocked` | `BLOCKED` returned, or a T2 revert | either |
| `blocked_on_human` | needs a human-only act; listed in the inbox; the writer moves on | coordinator |
| `stopped` | budget box exceeded, two substantive rounds, stall, or kill switch | coordinator |

Definition of Done: T1 green, review pass (and named-risk pass when applicable), merged, T2 green, ledger rows flipped with test name and log, `PROGRESS.md` note, no test removed or weakened.

## Implementer run

1. Orient: recent log in the worktree, the tail of `PROGRESS.md`, the brief, its ledger rows.
2. Environment: the project's init command; confirm the baseline smoke passes. A broken baseline is the first thing to fix.
3. Under the default cadence, take the highest-priority row with `passes: false`. Under candidate cadence, collect the related rows that deliver the slice outcome. Reuse existing code; ask an explorer when unsure.
4. Follow the configured [cadence](05-verification.md#candidate-cadence). Under the default cadence, make T0 green before the turn ends. Under candidate cadence, keep intermediate edits in the allocation until the complete slice is ready.
5. Commit; append one dated paragraph to `PROGRESS.md`; add a `FRICTION:` line if a manual step was repeated or a wait occurred.
6. When the goal condition holds, rebase if the integration head changed a file the slice also changed, run T1, return `CANDIDATE`.
7. Resumed with `FINDINGS`: repair in scope, run T1, return `CANDIDATE` again.
8. Resumed with a new brief: start at step 1; released: stop.

Stall rule: no commit for 90 minutes of wall time, or the turn limit, ends the run as `stopped`; the coordinator reads `PROGRESS.md`, splits or re-briefs, and re-dispatches. Absolute paths in every command: a subagent's working directory does not persist between tool calls.

## Decision

| Class | Examples | Who closes it | How |
|---|---|---|---|
| A1, human-only | credentials, money, legal and consent, real personal data, irreversible actions outside the repository, external communications in the owner's name | owner | inbox row with the exact ask; the run continues on other work; never defaulted |
| A2, product and method default | wording, policy values, which synthetic case to pilot | coordinator applies the recommended default and records it | `OWNER-DECISIONS.md` row with the default, the consequence of reversing, a 48-hour veto window announced in the status; reversible by a later decision |
| B, technical contract | data shapes, paths, state vocabulary, error codes | coordinator | one line under Decisions in `STATE.md`; affected slices notified; owner veto within one day |
| C, local implementation | layout, fixtures, naming, reuse | implementer | decide; note in `PROGRESS.md` if non-obvious |

States: `open → recommended → decided | defaulted | vetoed → applied`. A decision is revisited only through a new decision, never silently.

## Contract

`draft` (contract author) → `frozen` (committed to the integration branch with golden fixtures; file and SHA recorded in `STATE.md`) → `amended` (new SHA, fixtures updated, `CONTRACT` sent to every active implementer that pins it) → `retired`. A frozen contract is the only interface between slices; an implementer that needs something a contract does not give returns `BLOCKED`, never invents a field.

## Defect

| Where found | What happens |
|---|---|
| T0 or T1 | fixed in the slice before a candidate |
| review | finding → repair in the same slice → delta review |
| T2 after merge | merge reverted; slice returns to `repair` with the log |
| T3 or nightly | a new fix slice with its own brief; the row stays `passes: false` |
| escaped to a demo | retro item: why T1 and T2 missed it; a named invariant check is added or the affected-set computation is corrected |
