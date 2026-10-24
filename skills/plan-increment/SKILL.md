---
name: plan-increment
description: Plan one increment before it starts - surface map, reuse audit, decoupling review into cores and wires with lanes and hot files, dependency columns filled, and the first ready briefs. Use when the user or the coordinator says "plan increment N", "what can start now", "map the surface for these slices", "split this increment", or when a milestone enters planning or an increment is about to start.
license: Apache-2.0
metadata:
  source: sudo-sane/sliceworks
  version: 0.5.1
---

# Plan an increment

Method: `method/14-design-and-plan.md` and `method/04-preparation.md`. Output: `<state-dir>/plans/increment-<n>.md` plus the slice table in `STATE.md`.

1. **Surface map.** One explorer per planned slice, read-only: what exists, what is missing, with file references; shared facts first (entry points, lints, forbidden imports, numbering ledgers).
2. **Reuse audit.** One line per slice: reuse instead of rebuild, naming the package or function; dead or duplicate code to decide on.
3. **Decoupling review.** Seams to freeze first (contracts); cores that can start now on fixtures or a fake port versus wires that wait for a merge; lanes per writer; hot files to serialize by rebase. Split a slice whose brief would exceed 150 lines.
4. **Dependencies.** Fill `depends_hard`, `depends_soft` (with the stub plan) and `touches` on every slice row; run the ready detector; confirm the writer cap. In the increment's `## Increment <n>: <title>` section of `BACKLOG.md` (one per increment; write it if it is missing, never a range heading), replace the `Proposed slices (candidates)` line with the slice table of the cut slices.
5. **Briefs.** One ready brief per writer with the `brief` skill; move the increment to `started` once its defaults are recorded.
