# 14. Design and Plan

## Design artifacts

| Artifact | Content | Rule |
|---|---|---|
| `INVARIANTS.md` | the constitution in short form: one line per invariant, the binding documents at the end | changes only through a decision; reviewers check findings against it; the named-risk reviewer answers each as a question |
| `ARCHITECTURE.md` | the one living design, edited in place | a change cites the D entry that caused it; sections that adopt a proposal are labelled; the lint fails a change without a citation |
| `specs/` | formats and protocols; a version number in the name when the name is a format (`events-1.md`); status `draft`, `frozen` or `superseded by <name>` | a frozen spec has no `TODO`; a format change bumps the version; a superseded spec stays in place for the readers of its version and is never edited; the spec lint is the `spec` row's check |
| `SCENARIOS.json` | user scenarios, the layer above ledger rows: `id, title, stage, roles, segments, milestone, increment, proves[]` | every scenario of a milestone proves at least one row before the milestone is `accepting` |
| `MILESTONES.md` | per milestone: promise, success metrics, exit criteria, increments with exit demos, **gate families** with their rows, releases | the acceptance contract; the owner approves it once per milestone |
| `threat-models/<surface>.md` | one page per material surface: assets, actors, entry points, the invariants that hold, the tests that prove them | written at Design, read by the named-risk reviewer at Build and by the release checklist |
| `INDEX.md` | the Current table: every living document, what it governs, status (`current`, or `archived (D-n)` with the file under `archive/`), last reviewed, translation state; the precedence rule | anything outside the table is evidence or history; a current row past the review limit fails the lint, and so does one not reviewed since the newest pivot decision; archived rows are history and exempt |

**Gate families** are the classes of acts that close a milestone beyond engineering: owner acceptance, legal and consent, provider and money, operations and environments, security review, real data. Eight of fourteen gate families in the first run were human acts; listing them at Design is what lets the Build phase park rows on them instead of waiting.

**Design review** happens before Plan: a read-only reviewer tests the design's assumptions against the repository and the rounds, along four dimensions (correctness, architecture and principles, missing parts, ambiguity), ranks findings, and batches every open question with researched options at the end. A finding here costs a sentence; the same finding in code review costs a slice.

The `architect` is a subagent or session that writes only the design surfaces; the role guard enforces the list.

## Plan

`MILESTONES.md` carries the ordered increments of the milestone with their exit demos; `BACKLOG.md` keeps the slices per increment (chapter 3), in one `## Increment <n>: <title>` section per increment with its exit demo, scenarios, human acts and either its proposed slices or, once cut, its slice table. Every increment that `MILESTONES.md`, `FEATURES.json` or `NEEDS-HUMAN.md` names has its own section, however far ahead; a range heading (`## Increments 2 to 5`) is not allowed, and the design-doc lint fails both. Prevents: increments the plan and the owner's inbox refer to that the dashboard cannot show. The Definition of Ready and the three preparation stages are chapter 4. Two activities were ad hoc in the first run and are now part of the method:

**Increment planning** (`plan-increment`), run by explorers before an increment starts: a **surface map** (what exists and what is missing for each planned slice, with file references), a **reuse audit** (reuse instead of rebuild, one line per slice), a **decoupling review** (seams to freeze first; cores that can start now on fixtures versus wires that wait for a merge; lanes per writer; hot files to serialize by rebase), and the dependency columns of the slice table filled. Prevents: slices rebuilt from scratch; writers colliding on one file; idle slots while slices could start.

**Re-planning** (`refocus`), when a request or evidence changes the product rather than adding to it. **The trigger**: a change is a *pivot* when it alters the milestone promise in `MILESTONES.md`, a riskiest assumption in `SPARK.md`, an invariant, or thins a scenario of the current milestone; anything else is a *feature* and is placed by intake (chapter 17). The business analysis answers the question in one line (`Pivot: yes | no`) and intake branches on it. A pivot runs eight steps: pause active slices at a safe point (a candidate or a commit); record the pivot as a D entry carrying the `pivot` marker, with its evidence and what is dropped, added and moved; **audit** the product (below); re-derive increments and scenarios; re-run `design` for every surface the audit marked `amend`, each change citing the pivot D; re-map rows (ids never change; thinned rows keep theirs) and retire or amend contracts; mark paused slices with the increment they resume in and leave a visible re-plan marker on the timeline; resume with `plan-increment`. Prevents: a pivot placed as a feature; a pivot made in chat that leaves the ledger, the design documents or the contracts describing the old product.

**The refocus audit.** Between Record and Re-derive, the two intake analysts walk the whole product against the pivot decision, read-only: the business analyst over `SPARK.md`, `MILESTONES.md`, `SCENARIOS.json` and the scenario and gate rows; the system analyst over `ARCHITECTURE.md`, `INVARIANTS.md`, the contracts, the specs, the threat models and the Current table. Each returns a verdict table; the coordinator writes them into `refocus/<D-id>.md` (template `refocus.md`): one line per document, scenario, row, contract, spec and threat model, with a verdict `keep`, `amend` or `archive`, the reason, and the D it follows from. `keep` refreshes the row's last-reviewed date in `INDEX.md`; `amend` goes to `design` or to re-derive; `archive` runs the archive procedure. The owner reads one file. Prevents: an audit that exists only in the coordinator's head; a document nobody re-read after the product changed.

**Archiving.** A living document that the new focus contradicts is moved, never deleted and never edited: `git mv` to `<state-dir>/archive/<date>-<name>`; its `INDEX.md` row keeps its place with the archive path in the file column, status `archived (D-n)` and the archiving date as last reviewed. A replacement of the same name gets a new current row. A spec is superseded in place (`status: superseded by <name>`), because its version may still be read. A scenario is `thinned`, a row keeps its id, a contract is `retired` (chapter 3). The lint fails a brief or a contract that references an archived file. Prevents: a brief or contract built on a document the pivot retired; history that cannot be found.

**Thinning**: a row leaves the milestone only by a decision; it keeps its id and moves to a later milestone or to `thinned` with the decision reference. Prevents: silent scope loss.

## Slice types

| Type | Brief | Review | Used for |
|---|---|---|---|
| `feature` | 150 lines, eight sections | full; named-risk at material boundaries | the increments' rows |
| `fix` | under 50 lines: the failing check, the suspected cause, the stop conditions | expedited: one reviewer, one round, same day | a red nightly, an escaped defect, an incident |
| `process` | the adopted proposal and its metric | light | retrospective adoptions |
| `release` | the checklist of chapter 15 | the security review row | shipping |

`fix`, `process`, `release` and infrastructure slices carry `unblocks`: the product rows they serve (chapter 19). A slice whose work is source preparation on disjoint paths may be allocated `prepare-only`, without the gate and outside the writer cap; its handoff is a checkpoint, never a candidate.
