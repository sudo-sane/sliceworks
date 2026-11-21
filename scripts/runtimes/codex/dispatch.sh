#!/bin/sh
# sliceworks 0.8.2. Start one Codex worker process for one allocation record (method 19), or resume it.
#
#   dispatch.sh <allocation-id>                    start: `codex exec` in the allocation's worktree, in the background
#   dispatch.sh <allocation-id> --resume "<msg>"   resume the worker's thread with FINDINGS, a new brief or a HOLD answer
#   options: --wait (run in the foreground), --dry-run (print the command and the prompt, run nothing)
#
# Why a process and not a native subagent: a Codex subagent shares the parent's checkout and sandbox and carries no
# role in PreToolUse hooks. A worker process gets its own working directory (the slice worktree), a sandbox chosen
# by role (read-only for analysts and reviewers, workspace-write for writers), its role in SW_ROLE and in the
# worktree's role marker (both read by the hooks, lib.sh sw_agent_type), and a fresh context: the prompt is the
# role's profile plus one dispatch line built from the allocation record, nothing from the coordinator's chat.
#
# Output, read by status.sh, the collector and the dashboard: <outputs>/slices/<slice>/codex/<role>-<ts>.jsonl (the
# `--json` event stream; its thread.started event carries the thread id), .last (final message, first line the return
# shape), .err, and .done (exit status and time) when the process ends; the pid in the allocation's
# execution.pid_file (default <run>/<allocation-id>.pid) and in <run>/codex/<allocation-id>.pid, which the Codex
# coordinator's Stop hook watches; <run>/codex/<allocation-id>.log names the latest stream.
# Refuses while the kill switch is present, while the budget guard would refuse a dispatch, and, for writer roles,
# when SW_WRITER_CAP worker processes are already alive.
set -eu
here="$(cd "$(dirname "$0")" && pwd)"; PKG="$(cd "$here/../../.." && pwd)"
id=""; resume=""; resume_set=0; wait=0; dry=0
while [ $# -gt 0 ]; do
  case "$1" in
    --resume) resume="${2:?--resume needs a message}"; resume_set=1; shift 2;;
    --wait) wait=1; shift;; --dry-run) dry=1; shift;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    -*) echo "dispatch: unknown flag $1" >&2; exit 2;;
    *) id="$1"; shift;;
  esac
done
[ -n "$id" ] || { echo "dispatch: allocation id required" >&2; exit 2; }
input='{}'; . "$PKG/hooks/lib.sh"
sw_load_config || { echo "dispatch: no .sliceworks/config.env in $(sw_root)" >&2; exit 2; }
case "$id" in *[!a-zA-Z0-9_.-]*|.|..) echo "dispatch: invalid allocation id" >&2; exit 2;; esac
[ "$SW_CODEX_NETWORK" = 0 ] || { echo "dispatch: SW_CODEX_NETWORK=$SW_CODEX_NETWORK is unsupported; writers have no network; use gate-runner.sh for database gates" >&2; exit 2; }
command -v "$SW_CODEX_BIN" >/dev/null 2>&1 || { echo "dispatch: Codex CLI not found: $SW_CODEX_BIN. Set SW_CODEX_BIN in .sliceworks/config.env to an executable (macOS: /Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex)." >&2; exit 2; }
alloc="$SW_ROOT/$SW_STATE_DIR/allocations/$id.json"
[ -f "$alloc" ] || { echo "dispatch: no allocation record $SW_STATE_DIR/allocations/$id.json" >&2; exit 2; }
a() { jq -r "$1 // empty" "$alloc"; }
role="$(a .role)"; role="${role:-slice-implementer}"; slice="$(a .slice)"; [ -n "$slice" ] || slice="$id"
case "$slice" in *[!a-zA-Z0-9_.-]*|.|..) echo "dispatch: invalid slice id" >&2; exit 2;; esac
wt="$(a .worktree)"; case "$wt" in '') wt="$SW_ROOT";; /*) ;; *) wt="$SW_ROOT/$wt";; esac
[ -d "$wt" ] || { echo "dispatch: worktree $wt is missing; the coordinator creates it from a committed snapshot first" >&2; exit 2; }
pidf="$(a .execution.pid_file)"; pidf="${pidf:-$SW_RUN_DIR/$id.pid}"
case "$pidf" in /*) ;; *) pidf="$SW_ROOT/$pidf";; esac
[ -f "$SW_ROOT/$SW_STOP_FILE" ] && { echo "dispatch: STOP kill switch present ($SW_STOP_FILE)" >&2; exit 3; }
if [ -f "$pidf" ] && kill -0 "$(cat "$pidf")" 2>/dev/null; then echo "dispatch: $id already has a live worker (pid $(cat "$pidf"))" >&2; exit 3; fi
verdict="$(printf '{"tool_name":"Agent","tool_input":{"subagent_type":"%s"}}' "$role" | CLAUDE_PROJECT_DIR="$SW_ROOT" sh "$PKG/hooks/budget-guard.sh" | jq -r '.hookSpecificOutput.permissionDecisionReason // empty')"
[ -z "$verdict" ] || { echo "dispatch: $verdict" >&2; exit 3; }
show() { python3 "$here/agents.py" show "$role" "$1" --root "$SW_ROOT"; }
sandbox="$(show sandbox)"; model="$(show model)"; effort="$(show effort)"
if [ "$sandbox" = workspace-write ] && [ "$(cd "$wt" && pwd -P)" = "$(cd "$SW_ROOT" && pwd -P)" ]; then
  echo "dispatch: writers require a separate worktree; the coordinator checkout is protected" >&2; exit 2
fi
if [ "$sandbox" != read-only ] && [ "$resume_set" -eq 0 ]; then
  live=0
  for f in "$SW_ROOT/$SW_RUN_DIR"/*.pid; do [ -f "$f" ] && kill -0 "$(cat "$f")" 2>/dev/null && [ -f "${f%.pid}.writer" ] && live=$((live+1)); done
  [ "$live" -lt "${SW_WRITER_CAP:-3}" ] || { echo "dispatch: writer cap reached ($live of ${SW_WRITER_CAP:-3} worker processes alive)" >&2; exit 3; }
fi

if [ "$wait" -eq 0 ] && [ "$dry" -eq 0 ]; then
  # Detach into a new session so the worker outlives the coordinator's tool call and its process group.
  command -v "$SW_CODEX_BIN" >/dev/null 2>&1 || exit 2
  set -- "$0" "$id" --wait; [ "$resume_set" -eq 0 ] || set -- "$@" --resume "$resume"
  mkdir -p "$SW_ROOT/$SW_RUN_DIR/codex"; err="$SW_ROOT/$SW_RUN_DIR/codex/$id.dispatch.err"
  python3 -c 'import os, sys; os.setsid(); os.execvp("sh", ["sh"] + sys.argv[1:])' "$@" </dev/null >/dev/null 2>"$err" &
  echo "dispatched $id ($role, sandbox $sandbox) as pid $!; follow it with scripts/runtimes/codex/status.sh (launcher errors: ${err#"$SW_ROOT"/})"
  exit 0
fi

ts="$(date -u +%Y%m%dT%H%M%SZ)-$$"; dir="$SW_ROOT/$SW_OUTPUTS_DIR/slices/$slice/codex"; base="$dir/$role-$ts"
if [ "$resume_set" -eq 1 ]; then
  prev="$(cat "$SW_ROOT/$SW_RUN_DIR/codex/$id.log" 2>/dev/null || true)"
  thread="$(cat "$SW_ROOT/$SW_RUN_DIR/codex/$id.thread" 2>/dev/null || true)"
  [ -n "$thread" ] || thread="$( [ -f "$prev" ] && jq -r 'select(.type == "thread.started") | .thread_id' "$prev" 2>/dev/null | head -n 1 || true)"
  [ -n "$thread" ] || { echo "dispatch: no thread id recorded for $id; start it instead of resuming" >&2; exit 2; }
  prompt="$resume"; set -- exec resume "$thread"
else
  ref="$(a .message_ref)"; done_when="$(a .completion)"
  ret="CANDIDATE <T1 log path>, BLOCKED <reason and the default you would apply> or HOLD <reason>"
  case "$role" in *reviewer) ret="your REVIEW";; *analyst|researcher|code-explorer) ret="your analysis";; esac
  line="Allocation $id ($role, $slice): read $SW_STATE_DIR/allocations/$id.json and ${ref:-the brief it names}; verify it matches this worktree before any edit."
  [ "$role" != slice-implementer ] || line="$line Write $slice into .slice at the worktree root. Goal: ${done_when:-the completion condition of the allocation}. Commit $SW_STATE_DIR/handoffs/$id.md on your branch before returning."
  line="$line The first line of your final message is $ret."
  prompt="$(show instructions)

---

$line"
  set -- exec
fi
set -- "$@" --json -o "$base.last"
# exec resume has no -s flag on the installed CLI; the same explicit config selects its sandbox.
if [ "$resume_set" -eq 1 ]; then set -- "$@" -c "sandbox_mode=\"$sandbox\""; else set -- "$@" -s "$sandbox"; fi
[ -z "$model" ] || set -- "$@" -m "$model"
[ -z "$effort" ] || set -- "$@" -c "model_reasoning_effort=\"$effort\""
if [ "$sandbox" = workspace-write ]; then
  # Grant only this worktree, objects and exact branch/reflog files (including their lock files).
  prepare=""; [ "$dry" -eq 1 ] || prepare="--prepare"
  roots="$(python3 "$here/writer_roots.py" "$SW_ROOT" "$wt" "$SW_OUTPUTS_DIR" "$SW_RUN_DIR" --integration "$SW_INTEGRATION_BRANCH" --branch "$(a .branch)" $prepare)"
  set -- "$@" -c "sandbox_workspace_write.writable_roots=$roots"
  set -- "$@" -c "sandbox_workspace_write.network_access=false"
fi
set -f
for x in ${SW_CODEX_EXEC_ARGS:-}; do
  case "$x" in -c*|-s*|-P*|-p*|-C*|--config*|--sandbox*|--permission*|--profile*|--full-auto*|--dangerously*|--enable*|--disable*|--add-dir*|--cd*|--search*)
    echo "dispatch: security overrides are forbidden in SW_CODEX_EXEC_ARGS: $x" >&2; exit 2;;
  esac
  set -- "$@" "$x"
done
set +f
set -- "$@" -c 'approval_policy="never"' -c 'web_search="disabled"'
run="$SW_ROOT/$SW_RUN_DIR/codex/$id"
metrics="$run/metrics"
line="Worker artifacts: SW_CODEX_RUN_DIR=$run; SW_METRICS_DIR=$metrics; SW_TIERS_FILE=$metrics/tiers.jsonl. Never write metrics to the coordinator state directory."
prompt="$prompt

$line"
if [ "$dry" -eq 1 ]; then
  printf 'cd %s && SW_ROLE=%s SW_RUNTIME=codex SW_ALLOCATION=%s %s' "$wt" "$role" "$id" "$SW_CODEX_BIN"; printf ' %s' "$@"; printf ' <prompt>\n--- prompt ---\n%s\n' "$prompt"
  exit 0
fi
command -v "$SW_CODEX_BIN" >/dev/null 2>&1 || exit 2
mkdir -p "$dir" "$metrics" "$SW_ROOT/$SW_RUN_DIR/codex" "$(dirname "$pidf")"
gd="$(sw_git -C "$wt" rev-parse --absolute-git-dir 2>/dev/null || true)"
case "$gd" in "$SW_ROOT/.git"|'') ;; *) printf '%s\n' "$role" > "$gd/sliceworks-role";; esac
printf '%s\n' "$base.jsonl" > "$SW_ROOT/$SW_RUN_DIR/codex/$id.log"
echo $$ >"$pidf"; echo $$ >"$SW_ROOT/$SW_RUN_DIR/codex/$id.pid"; rm -f "${pidf%.pid}.writer"; [ "$sandbox" = read-only ] || : > "${pidf%.pid}.writer"
isolated_candidate=""; mode="$(a .mode)"
if [ "$SW_VERIFY_CADENCE" = candidate ] && [ "$sandbox" = workspace-write ] && [ "$role" = slice-implementer ] \
  && [ "${mode:-full}" = full ] && [ "$(a .worker.kind)" = cli ] && [ "$(a .worker.runtime)" = codex ]; then
  isolated_candidate="$alloc"
fi
status=0
( cd "$wt" && SW_ISOLATED_CANDIDATE_ALLOC="$isolated_candidate" SW_ROLE="$role" SW_RUNTIME=codex SW_ALLOCATION="$id" SW_PREHANDOFF_CMD="$SW_PREHANDOFF_CMD" SW_VERIFY_CMD="$SW_VERIFY_CMD" SW_T0_ARGS="$SW_T0_ARGS" SW_CODEX_RUN_DIR="$run" SW_METRICS_DIR="$metrics" SW_TIERS_FILE="$metrics/tiers.jsonl" CLAUDE_PROJECT_DIR="$SW_ROOT" exec python3 "$here/worker.py" "$id" "$SW_ROOT/$SW_RUN_DIR/codex" "$SW_CODEX_BIN" "$@" "$prompt" ) </dev/null >"$base.jsonl" 2>"$base.err" || status=$?
printf '%s %s\n' "$status" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$base.done"
# The marker names the role only while its worker runs; a later command of the coordinator in this worktree is the coordinator's.
case "$gd" in "$SW_ROOT/.git"|'') ;; *) rm -f "$gd/sliceworks-role";; esac
printf '%s %s\n' "${base#"$SW_ROOT"/}" "$(head -n 1 "$base.last" 2>/dev/null || echo "<no final message; see $base.err>")"
exit "$status"
