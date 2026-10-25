# 8. Budget and models

## Routing

| Work | Model tier | Why |
|---|---|---|
| coordinator | top tier, high effort (never maximum: subagents inherit the effort) | contract decisions, merge judgment, small context by design |
| slice implementers | mid tier | long runs, most tokens; capable with a good brief |
| ordinary review | mid tier | clean-context diff review |
| architect (Design phase) | the smartest model available, highest effort, pinned in the profile | the architecture, the acceptance contract and the threat models are read by every later phase; an error here costs a slice, an hour here costs tokens |
| named-risk review, contract author | top tier, highest effort, pinned in the profile | material judgment, rare |
| milestone efficiency review | top tier | trend reading over telemetry |
| explorers, lookups | cheapest tier | cheap, provisional |

Keep the subagent prompt cache at the longest TTL the host offers. The plugin's profiles pin these tiers; a project that wants another routing overrides a profile with its own agent file of the same name, which the host prefers over the plugin's.

## Holds and boxes

- **The run owns a fixed share of the provider's window; the owner keeps the rest** (default 85/15). Read usage before every dispatch, at every merge and hourly while slices are active: the host's usage tool, appended to `metrics/usage.jsonl` by the recording script. Each runtime has its own window. In the dual profile the coordinator's Claude readings go to `metrics/usage-claude.jsonl`, recorded by the Claude Code status line with `scripts/claude-usage-statusline.py`, because the dispatch hook judges the last row of `usage.jsonl` whatever its runtime; the dashboard shows one budget block per runtime. Dispatch hold at `WEEKLY_DISPATCH_HOLD` (default 80%) or `FIVE_HOUR_DISPATCH_HOLD` (default 90%): the dispatch hook refuses any subagent except read-only explorers while the last reading is at or above a hold, missing, older than 90 minutes, or taken before a reset. Stop line at `WEEKLY_STOP` (default 85%): the role hooks refuse further edits (commits stay allowed) so a running implementer commits what passes and returns `HOLD budget-stop`; the coordinator stops any implementer still running, records the hold, runs the hold timer in the background and ends its turn; the timer's completion after the reset wakes the session. Never spend to reach a target.
- **Messages are dispatches.** A follow-up to an idle worker chat starts a model turn even when no guarded process is launched; the holds above apply to it. At a hold the coordinator reads completed workers through files and handles (chapter 19) and wakes none of them until a verified reset or an explicit owner change.
- At a hard limit the coordinator waits for the reset and continues on its own; implementers interrupted by a limit are re-dispatched after the reset from their branch.
- Paid overage is off unless the owner turned it on with a cap.
- Each slice carries a budget box. Until three slices have merged, the box is "measure and record"; afterwards 1.5 times the median of merged slices. Exceeding it stops the slice for re-planning. Wall time spent waiting on gates is counted separately from work.
- Two substantive repair rounds in one family also stop the slice.
- Concurrency: the writer cap plus two coordinator helpers.

## Forecasting

Forecasts are published only as "scenarios merged per window, last three windows". Token estimates in a backlog are not used for anything.
