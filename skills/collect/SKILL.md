---
name: collect
description: Read what every worker has actually finished without asking anyone - run the sliceworks collector over the open allocations and report, per allocation, RUNNING, DONE, BLOCKED, HOLD, STALE-HANDOFF or STOPPED-NO-HANDOFF from process handles, branch heads, tier logs and committed handoffs; then take the next already-authorized bounded action. Use when the user says "what finished", "collect results", "did the slice return", "is the writer still running", "check the chats", or whenever the coordinator would otherwise send a status request.
license: Apache-2.0
metadata:
  source: sudo-sane/sliceworks
  version: 0.8.1
---

# Collect: completion from artifacts

Method: `method/19-allocation-and-completion.md`. Script: `${CLAUDE_PLUGIN_ROOT}/scripts/collect.py`.

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/collect.py" --root "$PWD"`. Ordinary
   collection reads artifacts and sends no messages. For Codex worker telemetry, add
   `--merge-worker-metrics` as the coordinator to import complete staging rows
   idempotently. Each `GATE` line (the `gate` field in JSON) shows the latest runner
   report. Match the requested identity and read the per-request receipt before acting.
2. Act on each state, without a message to the worker:
   - `RUNNING` or `QUEUED`: ongoing work; a live test or a wait in a resource queue is not a stall. Do nothing, and never start a duplicate writer.
   - `CANDIDATE-UNVERIFIED`: the handoff does not prove exact passing evidence. Reconcile the named artifacts first. Run the required gate only for a valid completed candidate, or return the slice to repair with the discrepancy.
   - `DONE`: read the handoff and its supporting evidence. Before starting review,
     check whether a reviewer allocation already covers the same writer and candidate
     SHA. Start review once and leave a candidate-cadence writer open so it can repair
     findings. Set that writer `collected` after acceptance or explicit abandonment.
     With the default cadence, set the allocation `collected` at this handoff.
   - `BLOCKED` or `HOLD`: read the handoff's blockers and the default the worker would apply; decide (class B) or route to the owner (A1); re-dispatch from the branch with a new allocation when unblocked.
   - `STALE-HANDOFF`: under candidate cadence, resume the same allocation to finish the changed candidate. Otherwise, the worker committed after writing the handoff; read the branch log; if the worker is gone, treat the last commit as a checkpoint and run the required gate yourself (chapter 19, execution identity).
   - `STOPPED-NO-HANDOFF`: under candidate cadence, resume the same allocation. Otherwise, nothing runs and nothing was written. Inspect the worktree (`git status`, `git log`), the stop-gate output and the worker's last message **read-only** before anything else; then either run the authorized gate on the checkpoint or re-dispatch with a fresh allocation. Never send "are you done".
   - `MISSING-WORKTREE`: recreate from the allocation's base and branch after the snapshot preflight, or close the allocation with a note.
3. Record what changed in `.run/coordinator-session.md` (allocation states, handles) and in `STATE.md`.
4. `UNREGISTERED` lines: work that no allocation owns (a worktree, a live pid, a running log). Register it as an allocation before acting on it; an empty registry is not a clean state.
5. A message to a worker is a dispatch for budget purposes, and the budget guard enforces it: at a dispatch hold, collect and do not wake anyone.
