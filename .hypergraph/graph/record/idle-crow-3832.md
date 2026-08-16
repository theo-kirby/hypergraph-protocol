---
node_id: 1e7d765c-ebf0-5b7c-a814-ad41ca66e500
slug: idle-crow-3832
title: 'State-graph shape measured post-reorg: offenders down ~40%, one-sitting still unmet'
created_at: '2026-08-16T18:13:09+00:00'
parents:
- even-journey-4120
summary: 'First post-reorganization measurement of this repo''s state graph: 25 nodes, 128.4 KB bodies, max node 11.9 KB, depth 2; every pre-reorg offender shrank ~40%, but a whole-graph read is ~101 min at 200 wpm.'
artifacts:
- .hypergraph/evidence/2026-08-16-state-shape-measure.py
- .hypergraph/evidence/2026-08-16-state-shape-baseline.json
---
## What

Measured the size and shape of this repo's own state graph — the first
post-reorganization measurement — with a reproducible, stdlib-only script, and
committed both the script and the full JSON baseline as evidence. This is the feed
`late-sage-5549` deferred the generalizable check rule to: numbers where the SPEC
convention ("the whole state graph should be readable in one sitting") previously
had none.

## Why

Child of the dispatch claim `even-journey-4120` (lane `weathered-eagle-6214`,
target chosen: `soft-hill-6082`). The State graph node holds the project's live
hypothesis and says the deferred size-and-shape `check` rule "is fed by what this
one measured" — but `late-sage-5549` measured only the *before* (174 KB of bodies
across 15 nodes). Without an *after*, the reorganization's effect is asserted, not
measured, and a future rule has no empirical envelope to pin thresholds to.

## Method

`python3 .hypergraph/evidence/2026-08-16-state-shape-measure.py
.hypergraph/graph/state --json
.hypergraph/evidence/2026-08-16-state-shape-baseline.json` at lane commit of this
node. The script is read-only, stdlib-only, and repo-independent: it splits
frontmatter from body, counts body bytes / words / bullets per node, parses
`Status:` and `parents:`, computes depth from the graph root, and aggregates
totals, histograms, frontier share, and reading time at 200 wpm. The JSON carries
the full per-node table; the script is the definition of every number below.

## Result

**After (2026-08-16): 25 nodes, 128.4 KB of bodies (146.0 KB of files), mean
5.14 KB, median 4.56 KB, max 11.9 KB, max 40 bullets, depth histogram 1/11/13
(root/depth-1/depth-2), frontier 5/25 (0.20).** Against `late-sage-5549`'s before
(174 KB across 15 nodes, worst node 19.4 KB, 51 bullets, flat):

- **The reorganization worked where it aimed**: total bodies fell 26% while the
  node count grew 15 → 25; the mean node fell ~56% (≈11.6 KB → 5.14 KB); every
  pre-reorg offender shrank ~40% — empty-forest-6305 19.4 → 11.9 KB,
  morning-crane-7863 18.8 → 11.05 KB (51 → 40 bullets), protocol-benchmark-4417
  17.6 → 9.67 KB (50 → 32), wandering-sun-8831 15.9 → 8.95 KB (48 → 37). Depth is
  real now: 13 of 24 non-root nodes sit at depth 2.
- **"One sitting" is still not met on a whole-graph read**: 20,204 words is ~101
  minutes at 200 wpm. The convention as worded is a whole-graph bound, and no
  per-node cleanup reaches it while node count grows. A rule that only bounds
  per-node size will pass a graph nobody can read.
- **The measured envelope gives the deferred rule discriminating thresholds**: a
  rule at (body > 12 KB or bullets > 40 per node) passes today's graph and would
  have flagged four nodes of the pre-reorg graph — exactly the separation a check
  needs. The whole-graph bound (total KB or reading minutes) is the part that
  still needs a decision, because today's graph fails any honest version of it.
- Incidental, found while verifying the suite in the lane: `pytest` is not
  lane-clean — `test_push_reports_actionably_when_no_transport_exists` asserts on
  the ambient checkout branch and fails in any worktree not on `main` (push
  stands down with the branch message before reaching the no-transport message).
  Green on `main` (302 passed, 2 skipped); 1 failed, 301 passed in the lane. No
  code was touched by this unit.

Evidence committed: `.hypergraph/evidence/2026-08-16-state-shape-measure.py`
(method), `.hypergraph/evidence/2026-08-16-state-shape-baseline.json` (full
per-node data).

Dispatch closed: 1 unit(s) — post-reorg state-graph shape measured; per-node cleanup confirmed (~40% on every offender), whole-graph "one sitting" still unmet at ~101 min

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: lane/weathered-eagle-6214
- commit: 7b7c6f19773553b16614a8fd8fbb5b1db45c36c6

## State Impact

- target: soft-hill-6082 — new claim: post-reorg shape measured (25 nodes, 128.4 KB bodies, max node 11.9 KB / 40 bullets, depth <= 2, frontier 5/25); every pre-reorg offender shrank ~40% vs the 174 KB/15-node baseline, but a whole-graph read is ~101 min at 200 wpm, so the one-sitting convention is still unmet — measured envelope (body <= 12 KB, bullets <= 40 per node) is the candidate threshold set for the deferred check rule
- target: wandering-sun-8831 — new claim: the test suite is not lane-clean — test_push_reports_actionably_when_no_transport_exists asserts on the ambient checkout branch and fails in any worktree not on main
