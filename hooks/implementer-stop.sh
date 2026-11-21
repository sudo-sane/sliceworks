#!/bin/sh
# sliceworks 0.8.2. Stop gate for slice implementers (method 3, step 4; method 5, T0): a turn may end only when T0
# is green in the implementer's worktree. Runs on SubagentStop (Claude Code subagents) and on Stop (a Codex worker
# process, whose role comes from its launcher); the main session has no role and passes. Escapes: stop_hook_active (already blocked once this
# turn), an explicit BLOCKED marker, an evidenced unavailable-command HOLD, the budget stop line, the kill switch.
input="$(cat)"; . "$(dirname "$0")/lib.sh"; sw_load_config || exit 0
sw_plugin_hooks_enabled || exit 0
type="$(sw_agent_type)"; sw_is_role "$type" slice-implementer || exit 0
[ "$(sw_field '.stop_hook_active')" = "true" ] && exit 0
cwd="$(sw_field '.cwd')"; [ -n "$cwd" ] || cwd="$(pwd)"
root="$(sw_git -C "$cwd" rev-parse --show-toplevel 2>/dev/null || echo "$cwd")"
case "$(head -n 1 "$root/.blocked" 2>/dev/null)" in BLOCKED*) exit 0;; esac
case "$(sw_budget_verdict)" in stop*) exit 0;; esac
[ -f "$SW_ROOT/$SW_STOP_FILE" ] && exit 0
# An unavailable-command HOLD must name the exact command and preserve its output.
if [ -f "$root/.blocked" ] && [ -f "$root/.prehandoff-unavailable.json" ]; then
  unavailable="$(jq -r '.command // empty' "$root/.prehandoff-unavailable.json" 2>/dev/null)"
  log="$(jq -r '.log // empty' "$root/.prehandoff-unavailable.json" 2>/dev/null)"
  case "$log" in /*) ;; *) log="$root/$log";; esac
  if [ "$unavailable" = "$SW_PREHANDOFF_CMD" ] && [ -s "$log" ] && grep -qF "HOLD" "$root/.blocked" && grep -qF "$unavailable" "$root/.blocked"; then exit 0; fi
fi
# In the opt-in, the collector distinguishes an intermediate return from a
# completed candidate. A HOLD or an unresolved allocation uses the old checks.
candidate_stop=LEGACY
if [ "$SW_VERIFY_CADENCE" = candidate ] && [ "$(sw_runtime)" = codex ] && [ -n "${SW_ALLOCATION:-}" ]; then
  candidate_stop="$(PYTHONDONTWRITEBYTECODE=1 python3 "$(dirname "$0")/../scripts/collect.py" \
    --root "$SW_ROOT" --state-dir "$SW_STATE_DIR" --candidate-stop "$root" \
    --allocation "${SW_ALLOCATION:-}" 2>/dev/null)" || candidate_stop=LEGACY
  case "$candidate_stop" in
    DONE|STOPPED-NO-HANDOFF|STALE-HANDOFF|BLOCKED) exit 0;;
    CANDIDATE-UNVERIFIED)
      jq -n '{decision:"block", reason:"Candidate lacks exact evidence from the configured verifier. Collect or fix its handoff before review."}'
      exit 0;;
  esac
fi
# Preserve the legacy unconfigured-project behavior only for the default T0 command.
script="$root/$SW_VERIFY_CMD"; [ -x "$script" ] || script="$SW_ROOT/$SW_VERIFY_CMD"
if [ "$SW_PREHANDOFF_CMD" = "$SW_VERIFY_CMD $SW_T0_ARGS" ] && [ ! -x "$script" ]; then
  if [ "$candidate_stop" = HOLD ]; then
    jq -n --arg r "HOLD needs a passing pre-handoff check or the exact unavailable-command record for $SW_PREHANDOFF_CMD."       '{decision:"block", reason:$r}'
    exit 0
  fi
  echo "sliceworks: T0 gate skipped, no executable at $SW_VERIFY_CMD (set SW_VERIFY_CMD in .sliceworks/config.env)" >&2
  exit 0
fi
if [ "$SW_PREHANDOFF_CMD" = "$SW_VERIFY_CMD $SW_T0_ARGS" ]; then
  out="$(cd "$root" && "$script" $SW_T0_ARGS 2>&1)"; status=$?
else
  out="$(cd "$root" && sh -c "$SW_PREHANDOFF_CMD" 2>&1)"; status=$?
fi
if [ "$status" -ne 0 ]; then
  log="$(printf '%s\n' "$out" | sed -n 's/^LOG=//p' | tail -n 1)"
  jq -n --arg r "Pre-handoff check is red in $root ($SW_PREHANDOFF_CMD, exit $status); fix it before HOLD or CANDIDATE. Log: ${log:-none}. Tail: $(printf '%s\n' "$out" | tail -n 25 | tr '\n' ' ' | head -c 2000)" \
    '{decision:"block", reason:$r}'
  exit 0
fi
# A HOLD may defer its database gate after this pass. A candidate still owes the original T0 gate.
[ -f "$root/.blocked" ] && exit 0
[ "$candidate_stop" = HOLD ] && exit 0
if [ "$SW_PREHANDOFF_CMD" != "$SW_VERIFY_CMD $SW_T0_ARGS" ] && [ -x "$script" ]; then
  out="$(cd "$root" && "$script" $SW_T0_ARGS 2>&1)"; status=$?
  if [ "$status" -ne 0 ]; then
    jq -n --arg r "T0 is red in $root (exit $status): $(printf '%s\n' "$out" | tail -n 25 | head -c 2000)" '{decision:"block", reason:$r}'
  fi
fi
exit 0
