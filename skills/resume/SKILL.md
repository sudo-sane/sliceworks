---
name: resume
description: Start or resume the sliceworks coordinator in a project that adopted the method - read the recovery file and the state files, record a usage reading, apply the budget holds, re-dispatch slices whose implementer is not running, restart the background timers, and set the increment goal. Use when the user says "resume the coordinator", "continue the run", "pick up where the run stopped", "restart after the compaction", or pastes the START page's resume prompt.
license: Apache-2.0
metadata:
  source: sudo-sane/sliceworks
  version: 0.8.0
---

# Resume the coordinator

Read `.sliceworks/config.env` for the paths below. If the kill switch file exists, stop and say so. Under Codex, every dispatch, resume, review, background timer and wait below goes through the Codex adapter, `${CLAUDE_PLUGIN_ROOT}/scripts/runtimes/codex/README.md`: workers are `dispatch.sh` processes and the Stop hook replaces the wake timer.

1. **Recover.** Read the open allocation records under `<state-dir>/allocations/` first (they are the unit of recovery; a chat preview or an old plan is not an allocation), then `.run/coordinator-session.md` if it exists (handles, background task ids, next actions), then `<state-dir>/START.md`, `STATE.md`, the tail of `PROGRESS.md`, and `NEEDS-HUMAN.md`. Do not read logs yourself; use explorers.
1b. **Collect.** Run the `collect` skill. Completion is read from handoffs, branch heads, logs and process handles, never requested; when a writer has stopped and the next bounded action is authorized, take it.
2. **Record usage.** Read the host's usage and append it to `<state-dir>/metrics/usage.jsonl` with the recording script (event `resume`).
3. **Apply holds.** At or above the dispatch hold do not dispatch anything. At or above the stop line stop every running implementer, write the hold into `STATE.md`, start the hold timer in the background and end the turn; when its completion wakes you, record a fresh reading and continue from step 1.
4. **Re-dispatch.** For a candidate-cadence allocation, use the collector's disposition. Continue an intermediate stop with the same allocation and resume a reviewed candidate only when the review returns `FINDINGS`. Under the default cadence, for every allocation the collector reports as stopped without a handoff, or every slice recorded `active` or `repair` whose implementer is not running, dispatch the `slice-implementer` agent from its branch with its brief and the `PROGRESS.md` tail, with the dispatch prompt of `method/07-communication.md` (`BRIEF`). Remove any `.blocked` marker first.
5. **Keep one ready brief per writer.** Run the ready detector; write briefs with the `brief` skill for slices that could start; dispatch into free writer slots, preferring the fewest shared hot areas.
6. **Background timers.** Start the dashboard loop (always: `sh scripts/sliceworks/dashboard-loop.sh 30`, installed by `adopt`) and the wake timer (while any slice is active) with `run_in_background`; when the wake timer completes, record a reading, act on its `STALL`, `STALE` and `READY` lines, and restart it.
7. **Update the recovery file** at every dispatch, merge and before an expected compaction.
8. **Goal.** Set the goal for the current increment: every ledger row of the increment is `passes: true` or `blocked_on_human`, the demo command passed, and the retrospective file exists. When the milestone's last increment closes, run the `accept` skill instead of starting another increment.

For candidate cadence, collect `DONE` for the exact checked SHA before starting review. Resume an intermediate stop in the same allocation; a `CANDIDATE` message only prompts collection. Keep the candidate-cadence writer open through review and any `FINDINGS` repair, following the collector's review allocation check. For each verified candidate, read the T1 evidence; spawn `code-reviewer` (and `named-risk-reviewer` when the brief says material boundary: yes); relay `FINDINGS`; merge by SHA with `git merge --no-ff`; run T2 in the background; flip the rows with evidence; record state; re-dispatch. Keep chat replies to a line or two; the dashboard carries progress.
