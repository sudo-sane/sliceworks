# Field report: merge on review, prove in a stream

Dated design note, frozen. Written 2026-10-17 from the first adopting project's run (package 0.8.2 installed locally, Claude Code and Codex hosts). Status: **field evidence and proposals; nothing here is implemented in the package yet.** The project changed its own copy of the process the same day; this note records what changed, why, and what the package should absorb so that the next project gets it without local patches.

## 1. What happened

- Database test tiers on one laptop took one to three hours under memory pressure. Three concurrent integration tiers drove every package to its 60-minute timeout, so the project dropped to one database slot and strictly serial tiers. Every candidate then queued behind every other candidate's T1, and writers sat idle waiting for a receipt.
- The owner first narrowed T1 (changed units, direct dependents, plus a fixed list of security suites when migrations or access code change) and batched T2 (one full closure per two to four merges, bisect on red). That still left the merge path blocked on the slot.
- Then the owner decided: **merges are never blocked by database test runs.** Writers run database-free checks only, then review, then merge. Every slice's new or changed tests and its must-pass list become *obligations*. One continuous serial stream runs them on the newest integration snapshot, first the obligations, then the security suites when migrations or access code changed, then a rotating full-suite shard. Failures go through a flake rerun, then attribution (the obligation's owner, or a per-test bisect for a regression), then a fix ticket worked in parallel with new work. Only the **watermark**, where every obligation has passed and the security suites are green, may be deployed, sealed, demoed or accepted. A migration becomes immutable only once it is in a deploy seal; before that it is fixed in place.

## 2. What the project had to change by hand (the cost of a policy change today)

One policy change touched eleven places:

- the process chapter (tier table, lifecycle states, Definition of Done, repair loop, failure table, review inputs, merge rule, glossary);
- both host instruction files;
- three role profiles (implementer step "run T1 then CANDIDATE", the CANDIDATE return shape with a T1 log path, reviewer inputs "the T1 log");
- the regenerated Codex role files;
- the project verifier.

Running Codex writers cannot be messaged mid-run. The only lever was the verifier, which the gate runner re-reads at each request. A marker file now makes it answer a writer's gate request (identified by `SW_ALLOCATION`) with `RESULT=NOT_RUN` and the new instruction. A gate that was already queued had to be killed by hand down its process tree, because the waiting loop's parent ignored TERM while its `sleep` child held it.

## 3. Proposals for the package

### P1 Test mode as configuration, not prose (high)
Add `SW_TEST_MODE=gate|stream` to `config.env`.
- Method chapter 5 states both modes.
- In stream mode:
  - the gate runner answers implementer requests with a NOT_RUN receipt carrying the instruction;
  - the implementer profile's pre-candidate step reads "the project's pre-candidate checks" (`SW_PRECANDIDATE_CMD`);
  - the CANDIDATE shape names "the pre-candidate log";
  - reviewers take "the pre-candidate log" and list obligations.

A policy change then edits one value, not eleven files. Profiles should never restate tier names; they should reference the configured step.

### P2 Obligations ledger and stream scheduler (high)
- `schemas/obligation.schema.json`, one row per obligation: slice, merge SHA, package, test, tags, source (diff, brief, ledger checks, security, reviewer, manual), status pending/passed/failed/flaky, ran-at SHA, log.
- `harness` commands:
  - `file <merge>` derives obligations from the first-parent diff (changed `Test*` bodies with their build tags), the brief's must-pass section, the ledger rows' checks, and the security suites when protected paths change;
  - `pending --head`;
  - `mark`;
  - `watermark`.
- A scheduler script handles the snapshot, the verifier's existing slot admission, the order (obligations, security, rotating shard), the isolated flake rerun, the per-test bisect over first-parent merges, TICKET/INVESTIGATE lines, and a local `stream-green/<n>` tag.
- An obligation closes only by a pass at a snapshot that contains its merge.
- The project is building this now as a tooling slice and can upstream it.

### P3 Watermark as the release gate (high)
- Demo, seal and deploy wrappers refuse any SHA that is not a watermark tag's commit, unless an override names a recorded owner decision.
- Acceptance requires a watermark at or after the increment's last merge, plus one full-suite pass.
- Chapter 15 should say this, and the `accept` and `release` skills should check it.

### P4 Migration immutability tied to the first seal (medium)
"An executed migration is never edited" is too strong while every test database is disposable. It forced renumbering and backstop gymnastics. Better: immutable once contained in a deploy seal or in any environment with non-disposable data; before that, fix in place under the same number and record the edit in the migration ledger.

### P5 Gate control for the coordinator (medium)
- `gate-runner.sh cancel <allocation>` cancels a queued or running request, writes a NOT_RUN receipt with a reason, and reaps the whole process group (start verifier runs in their own process group).
- A coordinator-writable allocation `policy` field (for example `db_tiers: off`) that the gate runner reads.
- This removes the marker-in-the-verifier workaround.

### P6 Continuing a retired coordinator's writers (medium)
- After a coordinator handover, the new session cannot message the old session's Claude subagents.
- The project re-dispatched a new implementer and named the old worktree path as its slice worktree. The harness made an unused worktree beside it.
- `new-worktree.sh` refused non-numeric slice ids (`slice-DT`), so it could not be used either.

Proposal:
- the `resume` skill documents an "adopt an orphan worktree" step: verify no live writer, record a new allocation round on the same worktree and branch, and pass that path explicitly;
- the worktree script accepts any slice id matching the allocation schema;
- the allocation record carries `writer_changed_from`.

### P7 Message cap exhausted with a real defect (medium)
- A Codex writer used its eight messages, then the delta review found a production defect.
- The project switched runtime: a Claude implementer on the same worktree.
- Chapter 7 should state the rule: a new allocation round on the same worktree is allowed, the cap counts per allocation round, and the runtime may change.

### P8 Combined findings across reviewers (low)
- Code and named-risk reviews of one candidate arrive separately. Sending two FINDINGS rounds wastes messages.
- Add a `findings.md` template with per-reviewer sections, severities and an "unchanged" section, sent once.

### P9 Reviewer checklist: vacuous negatives (medium)
- A required negative control passed for the wrong reason: the foreign-approver case ran after the file was already approved, so the status check rejected it first.
- Behind it was a real defect: the approver was never checked on the approve path.

Add to the code-reviewer profile:
- every negative control must fail for its stated reason;
- it asserts the rejection code and pointer, not only "rejected";
- the reviewer traces at least one negative to the line that refuses it.

Under stream mode reviewers also ran the database-free tests themselves. Encourage that.

### P10 Flake filter in the package, not in a session scratchpad (low)
- The isolated-rerun helper (serialized through the slot queue, `-p 1`) lived in a session's scratch directory and nearly got lost at handover.
- It belongs in the scheduler (P2) as the flake filter.

### P11 Success measures with an alerting cadence (low)
- Measures:
  - merge latency candidate→merged (target under 45 min median);
  - writer idle time on tests (target zero);
  - obligations closed within two stream cycles (≥ 90 %);
  - watermark age (under 6 h);
  - escaped regressions.
- A daily report is too slow for a 6-hour watermark target. Run the check, which needs no model, at every wake, alert on a miss, and send the full report every 6 hours.
- Ship it as a `harness` command and dashboard tiles.

### P12 Handover hygiene (low)
- A retired coordinator session stays open only so its background processes finish. Its stale polling loops were later flagged by the stale-process check.
- The handover template should list every background PID with its purpose, and say where each result lands as a file.
- The new coordinator reads files only and reaps the old loops once their results exist.

## 4. Evidence still missing

- The stream had not completed a cycle when this note was written.
- No measure has a value yet.
- The per-test bisect and the watermark tag are untested in production use.

The project will report merge latency, obligation closure and the first escaped regression (if any) after its first week. That is the point at which P1–P3 should be decided for the package.
