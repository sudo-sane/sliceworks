# <slice> <name>

<!-- sliceworks 0.2.0. At most 150 lines (a fix slice: 50). Type: feature | fix | process | release. Status: draft | ready | done. Milestone <id>, increment <n>. -->

1. Outcome (one sentence, as the user sees it)
2. Scenarios (FEATURES.json ids this slice flips)
3. Contract pins (file, SHA)
4. Reuse map (package or function, one line each)
5. Out of scope and held (with reasons)
6. Verification (exact commands with absolute paths; the end-to-end test name; test type per component: unit for logic, integration for adapters, contract for consumers, end-to-end for the scenario)
7. Decisions already made (STATE.md class B lines; OWNER-DECISIONS ids)
8. Stop conditions (when to return BLOCKED instead of guessing)

Material boundary: yes | no
Goal condition: <the condition the implementer must satisfy before returning CANDIDATE>
Dependencies: hard <slices whose merged code this needs>; soft <slices this can start without, with the stub plan>; touches <hot areas, for rebase risk>
Unblocks (fix, process, release and infrastructure slices only): <the product rows this work unblocks; it blocks nothing else>
Baseline: <full commit and the gate log of the base, so failures can be classified>

In Verification, link the accepted base and cumulative preparation scope (method chapter 5).
Name the first connected control, expected healthy and adverse outcomes, test selection,
and admitted environment. For a shared resource, list its users and the ownership, release,
and fault-control restoration witnesses. Record the observation or exact `NOT_RUN` reason in the handoff.
