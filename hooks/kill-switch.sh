#!/bin/sh
# sliceworks 0.8.9. STOP permits bounded inspection, never edits or dispatch.
# Unknown commands and classifier failures deny; method chapter 10 owns the rule.
input="$(cat)"; . "$(dirname "$0")/lib.sh"; sw_load_config || exit 0
sw_plugin_hooks_enabled || exit 0
stop="$SW_ROOT/$SW_STOP_FILE"
if [ -f "$stop" ]; then
  if printf '%s' "$input" | python3 -I -B "$(dirname "$0")/readonly-command.py" 2>/dev/null; then
    exit 0
  fi
  note="$(head -c 200 "$stop" 2>/dev/null | tr '\n' ' ')"
  sw_deny "STOP kill switch present at $stop ($note). Dispatch and edits are halted. Only allowlisted read-only commands are permitted while STOP remains present."
fi
exit 0
