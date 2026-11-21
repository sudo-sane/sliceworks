---
name: brief
description: Write one slice brief from its feature-ledger rows, the frozen contract and a reuse map - eight sections, at most 150 lines, material-boundary flag, goal condition, dependencies - into the slices directory. Use when the user or the coordinator says "write the brief for slice N", "brief this slice", "prepare slice N for dispatch", or when the ready detector lists a slice without a brief.
license: Apache-2.0
metadata:
  source: sudo-sane/sliceworks
  version: 0.8.1
---

# Write a slice brief

Template: `${CLAUDE_PLUGIN_ROOT}/templates/brief.md`. Method: `method/04-preparation.md`.

1. Collect: the slice's rows in `FEATURES.json`; the frozen contract (file and SHA from `STATE.md`); the decisions it depends on (`OWNER-DECISIONS.md` ids, `STATE.md` class B lines); the reuse map (ask one explorer for the packages and functions the slice should reuse, one line each; never read many files yourself).
2. Check the Definition of Ready (six conditions). If one fails, say which and stop; a brief for an unready slice is waste.
3. Write `<state-dir>/slices/<slice>-<name>.md` with the eight sections: outcome (one sentence, as the user sees it); scenarios (ledger ids); contract pins (file, SHA); reuse map; out of scope and held (with reasons); verification (exact commands with absolute paths; the end-to-end test name); decisions already made; stop conditions (when to return `BLOCKED` instead of guessing). Then `Material boundary: yes | no`, `Goal condition: ...`, and `Dependencies: hard ..., soft ... (stub plan), touches ...`.
4. Keep it under 150 lines. If it does not fit, the slice is too large: propose the split and stop.
5. Set the slice `ready` in `STATE.md` with the dependency columns filled.

Before the dispatch, write the **allocation record** `<state-dir>/allocations/alloc-<slice>-r<n>.json` from `templates/allocation.json` (schema `schemas/allocation.schema.json`): worker kind and runtime, worktree, branch, the **full 40-character base commit** (and its kind: integration, stacked, companion), allowed paths (the same list the role guard and the diff gate use), the completion condition, the required artifacts, the brief as `message_ref`, the `baseline` (the base commit's gate log and result, with its known debt assigned), `unblocks` for fix, process, release and infrastructure slices, and `mode` (`full`, `prepare-only`, `review`). Commit it. A worktree is created only from a committed snapshot that passes the project's preflight.

The dispatch prompt is one line (under Codex, `scripts/runtimes/codex/dispatch.sh` builds it from the allocation record): the brief path, the allocation id, the instruction to write the slice id into `.slice`, the goal condition, the three return shapes, and the rule that the worker commits `handoffs/<allocation-id>.md` (template `handoff.md`) on its branch before returning.

Under candidate cadence, name the decisive connected control in the brief and use the configured complete T1 verifier. Otherwise, for Codex writers, specify the database-free lint and tests in `SW_PREHANDOFF_CMD`, and verify the runner honors `SW_TIERS_FILE` and `SW_METRICS_DIR`. Database verification follows the adapter's request protocol; a brokered gate never excuses local pre-handoff checks. Keep `SW_CODEX_NETWORK=0`.
