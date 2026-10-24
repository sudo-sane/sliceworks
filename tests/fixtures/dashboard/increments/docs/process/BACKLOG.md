# Product backlog

## Increment 0: walking skeleton

Exit demo: the service starts and answers. Scenarios: R-001. Human acts: none.

| slice | state | content | depends on | writer |
|---|---|---|---|---|
| slice-01 service skeleton | merged | the process and its health check | none | slice-implementer |

## Increment 1: import

Exit demo: an imported file is listed. Scenarios: R-002. Human acts: NH-01.

| slice | state | content | depends on | writer |
|---|---|---|---|---|
| slice-02 import job | active | CSV import | none | slice-implementer |
| slice-03 import report | draft | a report of the import | slice-02 | slice-implementer |

## Increments 4 to 5

Exit demos: export, then the signed release. Proposed slices: export job; signing; release notes.
