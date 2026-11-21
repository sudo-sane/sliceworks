---
allocation: alloc-<slice>-r<n>
result: CANDIDATE | BLOCKED | HOLD
head: <full 40-character commit>
base: <full 40-character commit the work was built on>
verification: {tier: t1, log: <path>, result: pass | fail | NOT_RUN}
gate_request: <request ID for a brokered gate; omit for other verifiers>
proof_state: compiled | executed | runtime-verified
written: <timestamp>
---

# Handoff <allocation>

<!-- sliceworks 0.6.0. Committed by the worker on its branch before it returns (method chapter 19). The CANDIDATE, BLOCKED or HOLD message is a pointer to this file; this file is the record. -->

## Completed scope
<rows flipped, files changed in one line each>

## Verification
<what ran, from which commit, with which boundary (compile-only, executed, runtime); the RESULT line; what was NOT_RUN and why>

<for candidate cadence, name the host gate request, use the exact checked source in head, and commit only this handoff above it>

<accepted base, cumulative preparation log and scope limits; connected healthy and adverse observations with timestamps, or the missing precondition>

<if reusing evidence, link its original head, base and scope, the applicability decision and the fresh affected check>

## Failures, classified
<!-- against the allocation's baseline: a failure is introduced (absent on the base), inherited (present on the base; still blocks a mandatory gate, assigned, never waived), setup (NOT_RUN, the workload never started; the known remedy), or unproven (cause not established; stays red) -->
| check | class (introduced, inherited, setup, unproven) | evidence | assigned to |
|---|---|---|---|

## Findings decided out of scope
<id: reason>

## Blockers
<what stops the next step; the default the worker would apply>

## Next bounded action believed authorized
<one sentence, or "none">

## Stop gate output
<what the T0 gate printed on the last turn, verbatim first line>
