# Coordinator session state (read first after a context compaction)

<!-- sliceworks 0.2.0. Gitignored under .run/. Authority is STATE.md; this file holds what only the conversation knew. Update at every dispatch and merge and before an expected compaction. -->

Updated: <timestamp>

## Where we are
- increment, state, what merged last, what is in review

## Open allocations (authority: <state-dir>/allocations/*.json; this is the quick view)
| allocation | slice | role | worker id | handle or pid | last collector state | since |
|---|---|---|---|---|---|---|

## Background tasks
| task | id | since |
|---|---|---|

## Next actions
1.

For repeated repair, link the findings or recovery entry from chapter 19 with the
outcome, issue family, failed-cycle count, predicted evidence and next observed result.
