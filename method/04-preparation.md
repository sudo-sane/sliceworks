# 4. Preparation

## Definition of Ready

A slice may start when all six hold:

1. Outcome and scenarios named in `FEATURES.json`.
2. Contract frozen and committed with golden fixtures.
3. Every human-only act it depends on is done, or the slice is reshaped not to depend on it; every A2 default and B decision it needs is recorded.
4. Reuse map written.
5. Verification named: the exact commands and the end-to-end test.
6. Workspace allocated: worktree, environment prefix, ports.

Budget: two hours of coordinator time per slice. The coordinator keeps at least one ready slice per writer; that is the pull signal.

## Three stages, one artifact each

**Stage 1, contract.** Coordinator plus contract author, about an hour. Output: the interface hunk with real paths or signatures, data shapes, state transitions, error codes, three to five decisive examples (valid, refusal, failure), golden fixtures, committed to the integration branch.

**Stage 2, brief.** Coordinator, half an hour. At most 150 lines, eight sections plus the material-boundary flag, the goal condition and a Dependencies section (template in `templates/brief.md`). If it does not fit, the slice is too large; split it.
Use the [preparation and first behavior evidence rules](05-verification.md#preparation-and-first-behavior-evidence)
when writing Verification. Set the accepted base in the allocation as described in
[chapter 19](19-allocation-and-completion.md).

**Stage 3, self-planning.** Implementer, first fifteen minutes. Reads the brief, explores, writes its own short plan into `PROGRESS.md`. Nobody writes a task list for someone else.

Preparation in progress: one slice ahead per writer. No readiness frontier, no gap maps, no decision memos.

## Dependencies and capacity

The slice table carries `depends_hard` (needs merged code), `depends_soft` (can start on fixtures or a fake port, then rebase) and `touches` (hot areas, for rebase risk). A ready-detection script prints the slices that could start now and the free writer slots; the coordinator dispatches the one with the fewest shared hot areas. The writer cap is bounded by verification capacity first: no more full allocations than the shared verification slots can serve within the T1 budget (two database slots serving ten writers produced hour-long T1 runs and stale bases in the first run). Within that bound it falls by one when the median T1 of the last five runs exceeds 40 minutes or usage reaches 70% of the window, and rises by one when that median is under 20 minutes. Prepare-only allocations on disjoint paths do not count against it; they count against the budget. A live test or an orderly queue is work in progress, never a reason for a duplicate writer.

For material-boundary slices a plan review happens before code: a read-only reviewer checks the implementer's plan against a checklist of recurring defect classes. It is cheaper than the same finding in code review.
