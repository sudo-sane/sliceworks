#!/bin/sh
# sliceworks 0.8.1. Host-only, deterministic database gate broker; no model in the loop.
set -eu
here="$(cd "$(dirname "$0")" && pwd)"; PKG="$(cd "$here/../../.." && pwd)"
[ -z "${SW_ROLE:-}" ] || { echo 'gate-runner: host launcher only; never run inside a writer sandbox' >&2; exit 2; }
input='{}'; . "$PKG/hooks/lib.sh"
sw_load_config || { echo 'gate-runner: no project configuration' >&2; exit 2; }
export SW_ROOT SW_STATE_DIR SW_OUTPUTS_DIR SW_RUN_DIR SW_VERIFY_CMD SW_STOP_FILE
export SW_VERIFY_CADENCE SW_PREHANDOFF_CMD SW_T0_ARGS
exec python3 "$here/gate_runner.py" "$@"
