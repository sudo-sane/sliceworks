#!/bin/sh
# sliceworks 0.8.1. Budget hold (methods 8 and 19). A dispatch, which includes any message that wakes a worker chat, is refused while the last recorded usage
# reading is at or above a dispatch hold, when no reading exists, when it is older than SW_READING_MAX_AGE
# seconds, or when a reset has passed since it was taken. Read-only explorers (SW_EXPLORER_AGENTS) are exempt.
input="$(cat)"; . "$(dirname "$0")/lib.sh"; sw_load_config || exit 0
sw_plugin_hooks_enabled || exit 0
tool="$(sw_field '.tool_name')"; hit=0
for t in $SW_DISPATCH_TOOLS; do case "$tool" in *"$t"*) hit=1;; esac; done
[ "$hit" = 1 ] || exit 0
[ ! -f "$SW_ROOT/$SW_STOP_FILE" ] || sw_deny "STOP kill switch present at $SW_ROOT/$SW_STOP_FILE. Dispatch and worker messages are halted, including read-only explorers."
if [ "$tool" = "Agent" ]; then
  type="$(sw_field '.tool_input.subagent_type')"
  for e in $SW_EXPLORER_AGENTS; do [ "$type" = "$e" ] && exit 0; done
fi
f="$SW_ROOT/$SW_USAGE_FILE"
[ -s "$f" ] || sw_deny "No usage reading is recorded in $SW_USAGE_FILE. Read the host's usage, record it (sliceworks record-usage dispatch), then dispatch."
last="$(tail -n 1 "$f")"; now=$(date -u +%s)
at="$(printf '%s' "$last" | jq -r '.at // empty')"; at_s=$(sw_epoch "$at")
weekly="$(printf '%s' "$last" | jq -r '.weekly_pct // 0')"; five="$(printf '%s' "$last" | jq -r '.five_hour_pct // 0')"
wreset="$(printf '%s' "$last" | jq -r '.weekly_reset // empty')"; freset="$(printf '%s' "$last" | jq -r '.five_hour_reset // empty')"
for r in "$wreset" "$freset"; do
  [ -n "$r" ] || continue; rs=$(sw_epoch "$r")
  if [ "$rs" -gt 0 ] && [ "$now" -ge "$rs" ] && [ "$at_s" -lt "$rs" ]; then
    sw_deny "The last usage reading ($at) predates a reset ($r). Record a fresh one, then dispatch again."
  fi
done
age=$(( now - at_s ))
[ "$age" -le "$SW_READING_MAX_AGE" ] || sw_deny "The last usage reading ($at) is ${age}s old (limit ${SW_READING_MAX_AGE}s). Record a fresh one, then dispatch again."
w=${weekly%.*}; v=${five%.*}
if [ "${w:-0}" -ge "$SW_WEEKLY_DISPATCH_HOLD" ] || [ "${v:-0}" -ge "$SW_FIVE_HOUR_DISPATCH_HOLD" ]; then
  sw_deny "Budget hold: weekly ${weekly}% (dispatch hold ${SW_WEEKLY_DISPATCH_HOLD}%, the owner keeps ${SW_OWNER_SHARE_PCT}%), five-hour ${five}% (hold ${SW_FIVE_HOUR_DISPATCH_HOLD}%) at ${at}; weekly resets ${wreset}, five-hour resets ${freset}. Do not dispatch. At the stop line (${SW_WEEKLY_STOP}%) stop running implementers, record the hold in STATE.md, start the hold timer in the background and end the turn."
fi
exit 0
