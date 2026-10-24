---
name: retro
description: Close an increment under sliceworks - run the demo, spawn the efficiency reviewer, hold the retrospective (outcome and tax numbers, component table walk, at most three adopted changes with metrics and sunsets, last time's changes verified or sunset), write the retrospective page and notify the owner. Use when the user or the coordinator says "close the increment", "run the retro", "retrospective for increment N", or when every row of the increment is passing or blocked on a human.
license: Apache-2.0
metadata:
  source: sudo-sane/sliceworks
  version: 0.5.1
---

# Close an increment

Method: `method/03-lifecycles.md` (Increment), `method/09-metrics-and-improvement.md`.

1. **Demo.** Run the project's demo command for the increment; it must write `<state-dir>/demos/increment-<n>/demo.md` with every exit scenario's result. More than one failing scenario holds the next increment until the retrospective names the cause.
2. **Efficiency review.** Spawn the `efficiency-reviewer` agent with the increment number and the inputs (metrics files, friction lines, the proposals log, the method). It returns two paths and the proposal ids.
3. **Numbers.** Compute the three outcome numbers and four tax numbers for the increment from the state files and telemetry (the status script does this); compare with the previous increment. Add the coordination numbers of chapter 19: review rounds per slice, repeated unchanged checks, coordinator turns, messages to workers, and time allocations spent stopped without a handoff or waiting on a queue; accepted outcomes stand next to them, so artifacts are never read as progress.
4. **Component walk.** For each row of `method/11-components.md`, did its failure occur this increment? If not, remove the component, unless it is a security invariant. Record each removal as a decision.
5. **Adopt.** At most three proposals, each with a metric and a sunset, each becoming a process slice with a brief. Set statuses in the run file and `PROPOSALS.md`. A proposal touching the human-only list, the holds, the scope or the binding documents goes to `NEEDS-HUMAN.md` instead.
6. **Revisit.** Last retrospective's adopted proposals: `verified` if the metric moved, otherwise `sunset` and revert the change.
7. **Write** `<state-dir>/retros/increment-<n>.md` from `${CLAUDE_PLUGIN_ROOT}/templates/retro.md`: delivered, what review caught, what slowed delivery, process changes made, carried forward.
8. **Close.** Record milestones in `STATE.md`, set the increment `closed` in `STATE.md`, in its `MILESTONES.md` increments row and with a `Closed <date>` note in its `BACKLOG.md` section, start the next (`started` needs its defaults recorded, one ready brief per writer and its own `## Increment <n>: <title>` section in `BACKLOG.md`, never a range heading; the design-doc lint checks it), and notify the owner with the demo and retro links. This is one of the four notifications.
