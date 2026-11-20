# 19. Allocation and completion

The method's communication chapter assumed one thing the runtimes do not guarantee: that a worker's completion reaches the coordinator as a notification. In one host a worker is a subagent whose completion is delivered; in another it is a native chat, a CLI session and a long test, three actors with three lifecycles. A chat can finish while its process runs on; a process can finish without anyone being told; a message from one chat to another may need an authorization the sending session does not hold. The first run paid for that gap in stalls, redundant acknowledgements and wrong diagnoses. This chapter closes it: **completion is read from durable artifacts, never received from a message**, and the record that makes reading possible is the allocation.

## Actors

| Actor | What it is | Lifetime | What it owns |
|---|---|---|---|
| coordinator session | the one session on the integration branch | the run | the allocations, the ledgers, the merges |
| worker | a subagent, a native chat or a CLI session carrying one role (implementer, reviewer, named-risk reviewer, architect, auditor, contract author) | one allocation, resumable | its worktree, its branch, its handoff |
| execution | the process that runs a tier, a demo or a long command for a worker or the coordinator | one command | its log, its `RESULT=` line, its exit code |
| verification run | a tier run with its log and its `tiers.jsonl` row | one run | the result for one source identity |

A chat being active says nothing about whether a writer or a test is running, and a chat being idle says nothing about whether its process has finished. The coordinator distinguishes **chat activity** from **implementation activity** from **test activity**, and reads each from its own evidence: the process handle or pid for execution, the branch head and the handoff for implementation, the log and the tiers row for verification.

## The allocation record

Nothing is dispatched without an allocation record, `allocations/<id>.json` under the state directory, committed by the coordinator (schema `schemas/allocation.schema.json`):

| Field | Meaning |
|---|---|
| `id`, `slice`, `role` | what is allocated to whom |
| `worker` | kind (`subagent`, `chat`, `cli`), runtime, the acting worker's id, and `chat_id` when a native chat brokers a separate execution session: two actors, two identifiers |
| `execution` | the execution `session_id` when it differs from the chat, the pid file and handles of long commands, the log directory, and a `queue_marker` whose presence means a legitimate wait for a shared resource |
| `baseline` | the gate health of the base commit at dispatch: its log, result and the known debt already present, each item assigned; without it a candidate's failures cannot be classified |
| `mode` | `full`; `prepare-only` for source work on disjoint paths without the gate, beyond the writer cap; `review` for a read-only allocation |
| `unblocks` | for fix, process, release and infrastructure allocations, the product rows the work unblocks; such an allocation blocks only those rows and nothing else |
| `worktree`, `branch`, `base` | where it works, on which branch, from which **full 40-character** commit; a stacked or companion base is recorded as such |
| `accepted_base` | the already accepted full commit used for cumulative preparation (chapter 5); specify it for stacked and companion work, and default to the assigned integration base otherwise |
| `allowed_paths` | what it may write; the role guard and the diff gate enforce the same list |
| `completion` | the condition under which the allocation is complete, in one sentence |
| `required_artifacts` | what must exist for the coordinator to call it complete: the handoff, the tier log, the review file |
| `message_ref` | the brief or findings file the dispatch pointed at |
| `state` | `open`, `stopped` (no live process, no handoff yet), `collected` (handoff read), `closed` |

The record is the unit of recovery. After a context compaction the coordinator reads the open allocations, their handles and their handoffs before anything else; a chat preview, a historical approval or an old plan is not an allocation. In the first run a compacted session resumed an obsolete task because it read its own history instead of the record.

## The handoff

A worker ends every allocation by writing a **handoff**, `handoffs/<allocation-id>.md` (template `templates/handoff.md`), committed on its branch before it returns, with: the result (`CANDIDATE`, `BLOCKED`, `HOLD`), the full head commit, the base it was built on, the verification it ran (tier, log path, `RESULT=`), the blockers, the findings it decided were out of scope and why, the next bounded action it believes is authorized, and what its stop gate actually said. The `CANDIDATE`, `BLOCKED` and `HOLD` messages of chapter 7 remain the only message shapes, and they are now pointers to the handoff: useful when the runtime delivers them, never the record.

## Collection

The coordinator collects completion from evidence. The [collect skill](../skills/collect/SKILL.md)
maps the collector's states to the next action. Adopt a running project by registering
unowned worktrees and live evidence into allocations first. Run the collector at resume
and after each wake. Any runtime chat inspection is read-only and secondary. Record
fine-grained progress in the result or handoff and finish the allocation with `collected`
or `closed`.

Rules that follow:

- **No acknowledgement is ever a prerequisite.** When a writer has stopped and the next bounded action is already authorized (the gate after a checkpoint, the review after a candidate, the merge after a pass), the coordinator proceeds. A live test or a legitimate resource queue is ongoing work, not a stall.
- **No status requests.** A message to a worker is a dispatch: it starts a model turn and counts against the budget holds of chapter 8, native chats included. At a dispatch hold the coordinator inspects completed workers through files and handles and wakes none of them.
- **Delivery failure is a diagnosis, not an assumption.** Before declaring that a message did not arrive, read what the worker received, what its stop gate printed and what it executed. In the first run a repeated instruction did nothing because the writer's stop gate kept redirecting it to pending verification; the fix was the diagnosis, not a third copy of the message.
- **Process handles are kept.** A long command is observed through the handle it was started with until it ends; a yielded tool call or an observation timeout is not a failure; a detached child of a finished shell is not a durable job. An interrupted command's real exit code and absent pid are recorded before anything resumes.
- **Repeats need a reason.** A check is rerun only for changed source, a new failure or a named missing proof, stated before the rerun. The same unchanged check passing four times is the cost this rule prevents.

## Execution identity

A result certifies exactly one source identity: the full commit it ran on, in the checkout it ran in, against the base the allocation names.

- Verification names its commit in full; an eight-character head in a metrics row is bound to the verified full commit, never compared with one.
- A pin of the merge-gate checkout takes a full commit, never `HEAD`, which resolves inside that checkout and may leave the previous pin in place. The pinned commit is verified before any input is read or test started; a mismatch is a `NOT_RUN` setup failure, not a failed gate to retry. A live merge gate is never re-pinned.
- A stacked or companion worktree is checked against its **assigned** base and ancestry; a generic check against the moving integration head rejects valid preparation work. Nothing is rebased or renamed to satisfy a base the allocation did not name.
- A worktree is created only from a committed snapshot that passes its own preflight (for a project with numbered migrations: matching pairs, unique versions); a clean checkpoint whose deletions live only in another working tree is not a valid base.
- A result from a different base, checkout or commit never certifies the current candidate.
- Keep fresh executions and reused evidence distinct. Reuse cites the original result,
  source and scope, the independent applicability decision, and fresh checks of the
  affected boundary. A handoff-only publication can point to the verified source if its
  delta contains only the allocation's committed handoff and the project treats that file
  as metadata. The [Codex adapter](../scripts/runtimes/codex/README.md#host-gate-protocol)
  describes how the collector checks this case.

## What a result proves

Three states, never conflated, each named in handoffs, briefs and ledger evidence:

| State | Established by | Does not establish |
|---|---|---|
| **compiled** | a build of the changed production packages, with their build tags, and of the test packages | that anything ran |
| **executed** | the tests ran under the execution boundary that was intended (a compile-only check must prevent even package initialisation and `TestMain`) | that the product works end to end |
| **runtime-verified** | the scenario or demo ran against the real dependency from the pinned commit, with the log | acceptance by the owner |

Launch, cache, sandbox and output failures before a check starts are `NOT_RUN`: the known remedy is recorded once, in the project's `RUNTIME.md` (restriction, symptom, authorized remedy, decision), and no further writer turn rediscovers it.

**Failures are classified against the baseline** recorded in the allocation: *introduced* (absent on the base), *inherited* (present on the base; it still blocks a mandatory gate and is assigned to a slice or a debt row, never waived), *setup* (`NOT_RUN`), *unproven* (cause not established; the gate stays red). The handoff carries the table; the coordinator assigns inherited debt explicitly before the next dispatch rather than letting the next slice discover it. Preparation checks for changed production code build the production package, not only the tests: a test-only build passed while production did not compile because a helper lived in a test file.

Configuration loading never owns execution. A shell that sources configuration into the process that runs a check can replace its arguments or exit zero before the check runs; the loader supplies values as data, and the process that owns the command, the result rows and the step counts is the one that reports them. A zero exit code or well-formed JSON with zero steps is not evidence that the intended command ran.

## Approval, preparation, proof

A review pass approves **source**. A green preparation check establishes a **prepared** checkpoint. A runtime verification establishes **proof**. Tooling that passes its own gates is not accepted product. Each is recorded in its own words in state and ledger evidence, because the first run's code review passed where its named-risk review then found a real gap, and the runtime proof stayed open.

## Dependencies name what they block

Infrastructure, process and fix work is allocated with `unblocks`: the product rows it serves. It blocks those rows and nothing else; independent source work, pure checks, reviews and verification in a supported environment continue meanwhile. The ready detector prefers allocations that advance product rows, and the retrospective reads product rows passing next to tooling rows passing, because the first run spent review rounds on a baseline consolidation while independently executable product work stayed parked.

## Bounded repair

A failing round names the obstruction, preserves its result and log, and issues one
bounded correction to the same worker where possible. After two unsuccessful substantive
cycles on the same outcome and issue family, retain the count across allocation, task and
model changes. In the existing findings or recovery record, record the diagnosis, changed
strategy and the new observable result it predicts before the next attempt. Compare the
next observed result with that prediction and keep the comparison in the record. Correct
ordinary process, test harness and oracle failures under coordinator authority while other
ready work proceeds. Use the existing escalation path for decisions outside that authority.

## Where this leaves chapter 7

The six message shapes stand. What changes is their standing: a message is a courtesy to a runtime that can deliver it; the file is the record. "Never sent" still covers status requests and acknowledgements, and now also includes any message whose only purpose is to learn what a file already says.
