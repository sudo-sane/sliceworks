# 2. Topology and roles

## Topology

| Level | What | Count | Where | Lifetime |
|---|---|---|---|---|
| 0 | Owner | 1, optional after kickoff | notifications, the human inbox file, the dashboard | |
| 1 | Coordinator session | 1 | main checkout, integration branch | the whole run |
| 2 | Slice implementers | up to the writer cap | coordinator subagents with worktree isolation, one worktree and branch each, resumable | one slice, then re-dispatched |
| 2b | Coordinator helpers | as needed | reviewers, named-risk reviewer, contract author, efficiency reviewer, explorers | minutes |
| 2c | Implementer helpers | as needed | read-only explorers | minutes |

Implementers are worktree-isolated subagents of the coordinator so that no human has to create sessions. Their worktrees and commits persist in git, so a coordinator restart loses nothing; the resume routine re-dispatches any slice whose branch is ahead of its recorded state. Spawn depth two: an implementer may spawn read-only explorers and nothing deeper.

In the **lite profile** one session holds levels 1 and 2 at once; the Stop hook (T0 gate) is the only enforcement, and the state files are kept by the same session.

## Roles

**Owner.** One kickoff session, then optional. Performs the human-only acts when the inbox lists them, in their own time. May veto any recorded default within its window, stop the run with the kill switch, or read the status, the dashboard, the demos and the pull requests. Is never required to read worker transcripts, answer in chat, or relay messages.

**Coordinator.** Keeps `BACKLOG.md`, `FEATURES.json`, `STATE.md`, `OWNER-DECISIONS.md`, `NEEDS-HUMAN.md` and the session recovery file. Decides class B questions and applies class A2 defaults. Freezes contracts, with a contract-author subagent when a slice introduces new interfaces. Writes briefs. Dispatches, resumes and re-dispatches implementers; waits on completion notifications rather than polling. On a candidate: checks the T1 log, spawns the reviewer, relays findings, merges by SHA, runs T2 in the background, records state, flips ledger rows. Runs T3 at milestones and the automated demo at increment ends. Runs the retrospective with the efficiency reviewer. Records usage readings at dispatch and merge. Writes no product code except merge resolution. Delegates every multi-file read to an explorer. May not change the binding documents, the meaning of a contract, the human-only list, the budget holds or the scope; those need the owner.

**Slice implementer.** One subagent, one worktree, one branch, one slice, its own environment. Owns the whole vertical of that slice. Plans its own work in the first fifteen minutes. Writes tests first where the behavior is clear. Runs T0 on every turn (hook) and T1 before a candidate. Commits after each passing row. Appends to `PROGRESS.md`. Returns only `CANDIDATE`, `BLOCKED` or `HOLD`. Repairs its own findings and decides which are in scope. Rebases onto the integration head when it changed a file the slice also changed. Never merges, never touches another worktree, never runs T3, never pushes, never contacts infrastructure. Bounded by a turn limit.

**Reviewer.** Fresh context, read-only tools. Input: base and head, the brief, the T1 log. Output: findings with severity, file and line, evidence, or a clean pass. Correctness and stated requirements only. Resumed for the delta review. Does not edit, does not spawn, has no merge authority.

**Named-risk reviewer.** Same inputs plus one named question. Used at the first implementation of a material boundary (the project lists its surfaces: access control, isolation, erasure, private data, grounding of generated claims, money). Separate verdict from the reviewer's. A security invariant: never pruned.

**Contract author.** On demand. Produces the frozen interface for one slice: paths or signatures, data shapes, state transitions, error codes, decisive examples and golden fixtures. Writes only the contract surfaces the project lists.

**Explorer.** Read-only. Returns paths, symbols and a short map.

**Researcher.** Read-only subagent, one research question, returns claims with sources and a verification verdict for a round's register (chapter 13). Writes only inside the open round.

**Architect.** Writes only the design surfaces (invariants, architecture, specs, scenarios, milestones, threat models; chapter 14) from decisions and rounds; never product code.

**Efficiency reviewer.** Persistent project memory, writes only under the retros directory. Once per increment reads telemetry and friction notes and writes at most three proposals ([improvement loop](09-metrics-and-improvement.md)).

There is no process-manager chat, no domain-lead chats, no preparation chat.

## Read-only roles write their own outputs

A read-only role (code reviewer, named-risk reviewer, brief drafter, efficiency reviewer, contract author) writes its full output to its own directory instead of passing it through the coordinator's context: reviews and incidents under `<state-dir>/reviews/` and `<state-dir>/incidents/`, brief drafts under `<state-dir>/slices/drafts/`, retrospectives under `<state-dir>/retros/`, contracts under `<state-dir>/contracts/`. A per-role PreToolUse hook allows Markdown files under exactly those directories of the main checkout and refuses everything else, including worktree copies. The role returns only its verdict, the file path and at most ten lines; the coordinator promotes drafts and sends review files to writers as FINDINGS. State files, tickets and promoted briefs stay coordinator-only, because they carry decisions. Why: re-typing reports and long briefs was the largest single drain on the coordinator's context in the first field run.
