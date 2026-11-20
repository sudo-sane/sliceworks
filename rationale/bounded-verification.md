# Bounded verification adoption

## Evidence and decision

The November 2026 sliceworks-desk experiment found late lint and duplication failures
after preparation had inspected only the last writer's delta. It also found incorrect
runtime selectors and inherited test oracles. Independent static and runtime intervals
overlapped during one verification round. These observations come from one cohort with
different selected checks in successive rounds. They support testing cumulative
preparation and earlier connected controls. Whole-cycle speedup and attributable token
or cash savings remain unknown.

At sliceworks 0.8.9 (`89177ab`), the Codex supervisor already served gate requests
through the configured project verifier. The project owned resource admission and the
collector read allocation and worker telemetry artifacts. The package had no
implementation under `harness/`. The broker supplied the assigned base but had no
separate accepted base or cumulative exposure, and a log could be associated with
unrelated tier evidence for the same abbreviated head. The bounded change uses the
existing broker, verifier, collector and handoff. See the
[verification method](../method/05-verification.md),
[execution identity](../method/19-allocation-and-completion.md#execution-identity)
and [adapter](../scripts/runtimes/codex/README.md#host-gate-protocol).

## Verification on the package

- `python3 -m unittest discover -s tests` passed 191 tests on Python 3.13. The
  new cases covered temporary Git worktrees, request admission, source and base
  binding, selector failures, slot restoration, repeat collection and terminal states.
- `sh tests/test_hooks.sh` passed all 93 checks.
- `claude plugin validate --strict .` passed plugin validation. The directory
  check reported an absent catalog icon and ignored macOS metadata.
- The Go smoke test wrapped `go test -json -count=1 -run '^TestAtoi$' strconv` with
  `--summary go-json --expect-passed 1` and observed one pass with exit 0.
  The same invocation with `-run '^TestSliceworksNoMatch$'` observed zero passes
  and returned wrapper exit 2 while Go exited 0.

The package checks exercised local processes and temporary repositories. They supply
no measurements of application delivery, installed provider activation or billing.

## Follow-up work

1. Configure one adopting project to consume the cumulative manifest in its existing
   cheap checks for two or three comparable accepted outcomes. Retain the original final
   gates and compare missed-input findings, first connected feedback and elapsed time
   using [the existing event sources](../method/09-metrics-and-improvement.md#metrics).
   This tests whether the observed failure modes recur in practice.
2. If manual verification transitions still dominate, evaluate overlap through that project's
   slot admission on two checks with documented input and output independence. Record
   interval endpoints and verify actual exit and cleanup. The package introduces no new
   execution scheduling because resource independence depends on the consuming project.
3. Automate cycle rollups after the pilot identifies reliable artifact fields for the
   acceptance, repair and coordinator events. Until then, the retrospective cites
   existing artifacts and marks absent inputs unknown.
