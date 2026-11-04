# 10. Autonomous operation

## What autonomous means

After the kickoff session, no human turn is required for the run to advance. The coordinator decides, dispatches, reviews, merges, demos, retrospects and continues through the increments until the engineering-complete state. The owner is notified, may veto, may stop, and performs the human-only acts at their own pace. Work that depends on such an act is parked as `blocked_on_human` and the writer moves on; the run never idles waiting for a person.

## The human-only list (class A1)

A human is asked, through `NEEDS-HUMAN.md` and a notification, for exactly these:

1. **Credentials and secrets** for any environment outside the developer's machine. The agent states where the secret must be placed and verifies presence by name; it never reads a secret into chat or a log.
2. **Money**: enabling or raising paid usage, opening provider accounts, any purchase.
3. **Legal and consent acts**: approvals of policy texts, consent wording shown to real people, acceptance decisions.
4. **Real personal data**: uploading or processing any real person's material. Everything before that runs on synthetic data.
5. **Irreversible actions outside the repository**: creating or deleting cloud resources, DNS changes, rotating production secrets, deploying anywhere but the isolated environment the owner provisioned.
6. **External communications** in the owner's name.
7. **Changes to this list, the budget holds, the scope or the binding documents.**

A project extends the list in its configuration; it never shortens it.

## Safety rails

- **Scope lock.** Only the accepted scope; defaults are drawn from recorded recommendations; a new product question with no recommended default becomes A1.
- **Veto windows.** 48 hours on A2 defaults, one day on class B decisions. A veto reopens only the affected slices.
- **Budget.** Holds and a stop line on the provider's window; per-slice boxes; overage only if the owner turned it on with a cap; pause and auto-continue at a limit.
- **Mechanical boundaries.** Worktree isolation enforced by the host; deny lists for pushes and infrastructure commands; secrets unreadable by rule; protected files enforced at the diff and by hook; implementers cannot merge; the coordinator cannot change the binding documents.
- **Stall and runaway control.** A turn limit per implementer; the 90-minute no-commit stall rule; the two-round repair stop; the budget box; a stall detector and a stale-process detector that wake the coordinator with `STALL` and `STALE` lines.
- **Kill switch.** The `STOP` file in the state directory, checked by hooks before every dispatch and edit and at every turn end. While it exists, bounded read-only inspection is permitted; edits, effect-capable commands and all worker dispatch remain halted, including messages and read-only explorers. Unknown or unclassifiable commands deny. Inspection never removes STOP or resumes the run; removing it resumes. The [hook policy](../hooks/README.md) defines the supported inspection forms.
- **Harness self-check.** A broken settings file or hook is visible within fifteen minutes (a preflight in the wake timer).
- **Audit.** Every default, decision, merge, demo and retrospective is a dated file in git.
- **Recovery.** A session recovery file outside git (`.run/coordinator-session.md`) with agent ids, background task ids and next actions, updated at every dispatch and merge and read first after a compaction or restart.

## Two runtimes

The method does not depend on one host, and it does not assume the host delivers completions: allocation records, handoffs and the collector (chapter 19) make completion readable in any runtime, including one where a worker is a native chat plus a CLI session plus a long test with three lifetimes. Agent profiles are the source; a sync script renders them to the second runtime's format and a parity check in T0 fails on drift. The hook bodies read both runtimes' hook input; where the second runtime does not name the acting agent, the launcher sets the role in the worker's environment and its worktree, never inferred from a prompt. A runtime that delivers no completion keeps the coordinator going from its stop hook, which waits on the workers' artifacts. The rules that differ between hosts live in one adapter document per runtime, never in the method.

Each project has one active source of hook enforcement and one set of skill names per runtime. A project-local installation with independent project hooks disables the package hooks and plugin loading; an installation that relies on package hooks keeps them active. Before a candidate or a hold, the writer runs the project's lint and every test on changed packages that does not require the unavailable resource, records the commands and results, and names the exact command and captured failure when a check cannot run. A deferred database gate does not defer those checks.

A writer's sandbox must not reach providers. When a runtime cannot prove local-only database access, a deterministic host runner consumes a bounded request, runs the project's verifier under its existing verification-slot admission, and returns a durable result and log; no model turn brokers the gate. Worker telemetry stays in writable output or run directories, then the coordinator imports it into canonical state. The [Codex adapter](../scripts/runtimes/codex/README.md) defines the runtime keys and file protocol.

## Known limits

A product default can be wrong in a way no test detects until the demo; the veto window and the demo artifact are the mitigation. Usage limits pause the run until the reset. The machine must stay awake and the host open; a restart requires the resume routine once. Human-only acts that arrive late leave their rows parked; the run finishes everything else and stops at the engineering-complete state with those rows listed.
