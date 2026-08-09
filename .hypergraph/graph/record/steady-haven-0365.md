---
node_id: 39abf797-1326-5518-a9d6-8e8d65288ea9
slug: steady-haven-0365
title: 'Viz phase 6: 500 nodes in 0.43s — and the bottleneck was not the one the plan named'
created_at: '2026-08-09T10:20:11+00:00'
parents:
- cold-rose-6963
summary: 'First paint at 500 nodes: 8.22s -> 0.43s. Measurement showed the blob field was 98% of it, not the O(n^2) sim; tile pruning and a sample budget fixed it.'
flywheel:
  node_id: bef7fb84-f75a-5f17-b30f-4ae956753183
  slug: jolly-hat-7422
  revision: 0
  pushed_at: '2026-08-09T10:47:13+00:00'
  content_sha256: ce62578fad59a8350fdaa19fe68d3319082bfd7c3d720e946ea187d4852f18b4
---
## What

Took the page to its scale target. First paint on a synthetic 500-record /
60-state graph went from **8.22s to 0.43s**. Added a Barnes-Hut quadtree, a grid
hash for card de-overlap and blob avoidance, tile-pruned blob sampling with a
render-wide sample budget, level of detail by zoom, a time window over the record
graph, and hyperedge collapse.

## Why

Follows `cold-rose-6963`. Everything so far was built and measured on 39 record
nodes. The declared target is ~500, and nothing had been checked against it.

## Method

The first move was to build the fixture and **measure before optimising**, which
turned out to matter: the obvious suspect was wrong.

`tools/fixtures/large/generate.py` produces 500 record nodes and 60 state nodes
deterministically — a mostly-linear spine with branches and merges, claims citing
their evidence, an unreconciled tail. `check` reports 0 violations on it, so it
exercises the real parsing path rather than a toy.

**Measured attribution**, by building the same page with blobs off:

| | first paint |
| --- | --- |
| as it stood | 8.22s |
| after Barnes-Hut alone | 7.11s |
| the same page with blobs disabled | **0.14s** |

So the O(n²) repulsion loop — the thing the plan named, and the thing I would
have guessed — was worth 1.1s of 8.2. **The blob distance field was 98% of the
cost.** Optimising the sim first was not wasted (it is why the rest is 0.14s) but
it was not the problem.

The field's cost is samples × terms. Both were attacked:

- **Tile pruning.** The sampling grid is walked in 24×24 tiles, and each tile
  builds its field from only the members, corridors and obstacles within their own
  influence radius of it. This is *exact*, not an approximation: a member further
  than `padding + smoothing` from a tile can only return a large positive distance
  there, so it can never win the smooth minimum inside it; an obstacle beyond
  `clearance + smoothing` cannot dent the boundary. The proof is what makes it
  safe — the 12-blob output is byte-identical to before.
- **A render-wide sample budget.** 720,000 samples are shared across the blobs in
  one render, so 12 blobs still get the full 60k each and 59 get 12k and coarsen.

Then the rest, as planned:

- **Barnes-Hut** (`js/quadtree.js`) replaces the pairwise loop above 120 nodes,
  with the exact loop kept below that as both the cheaper path and the reference.
- **Grid hash** replaces the 40-pass O(n²) card de-overlap and, separately,
  answers "which non-members reach into this blob?" — 30,000 box tests per render
  at 500 nodes, now a bounded query.
- **Level of detail**: secondary card lines drop below 0.58 zoom, all node text
  below 0.34, leaving a coloured box that still reads as a shape.
- **Time window** (All | 250 | 100 | 50 most recent by `chrono`): the 500-node
  timeline is 87,000px wide, which is not a drawing. The window drops nodes from
  the *layout*, so the world shrinks rather than being scrolled past.
- **Hyperedge collapse**: a claim folds to one puck carrying its colour and member
  count, from a button in its panel. A member cited by another expanded claim
  stays visible — it belongs to that one too. A collapsed claim's blob is not
  drawn, because the puck already says it.

## Result

| | before | after |
| --- | --- | --- |
| first paint, 500 nodes + 59 blobs | 8.22s | **0.43s** |
| timeline width, window 100 | 87,078px | 17,478px |

Every view opens at or above the 0.45 floor at 500 nodes, and switching views
costs under 0.1s. `tests/browser/test_scale.py` asserts first paint under 1.5s —
a budget set to catch the *return* of quadratic behaviour, not a 20% wobble.

The small-graph metrics baseline is **unchanged**, which is the point: none of
this was a visible trade.

**One real bug, found by the fixture rather than by review.** `lane_layout`
assumed a parent is always placed before its child, and raised `KeyError` when it
was not. A child can carry an earlier timestamp than its parent — a backdated
import, a skewed clock — and the first draft of the generator produced exactly
that. Such an edge simply cannot continue a lane, so it opens a new one; the
pending-edge bookkeeping needed the matching guard, since an unplaced parent never
incremented it. `test_lane_layout_survives_a_child_older_than_its_parent` covers
it. This would have crashed the viz on a real adopted graph, not only on a fixture.

Tests: 148 pass (was 143; +5 — the timing budget, view switching at scale, the
time window, collapse and expand, level of detail, and the backdated-parent case).
Checker: 0 violations, including on the new fixture.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: hg-viz
- commit: 52637c50db4c44714e0e6da18b56be89dd1b9a24

## State Impact

- target: polished-pond-2718 — the page meets its ~500-node scale target: first paint on a synthetic 500-record/60-state graph went from 8.22s to 0.43s, and the small-graph baseline is unchanged, so none of it was a visible trade. The load-bearing finding is that the plan's named suspect was wrong. Measured by building the same page with blobs disabled: the O(n^2) repulsion loop was worth 1.1s of 8.2 (Barnes-Hut alone: 8.22 -> 7.11s), while the blob distance field was 98% of the cost (the same page without blobs painted in 0.14s). Fixed by attacking samples x terms: the sampling grid is now walked in 24x24 tiles, each building its field from only the members, corridors and obstacles within their own influence radius — exact rather than approximate, because a member beyond padding+smoothing can never win the smooth minimum inside a tile and an obstacle beyond clearance+smoothing cannot dent the boundary, which is why the 12-blob output stayed byte-identical — plus a render-wide budget of 720k samples shared across blobs, so 12 blobs keep full resolution and 59 coarsen. Also landed: Barnes-Hut quadtree (js/quadtree.js) above 120 nodes with the exact loop kept below as both the cheaper path and the reference; a grid hash replacing the 40-pass O(n^2) card de-overlap and the 30,000-box-test blob avoidance scan; level of detail by zoom (secondary card lines below 0.58, all node text below 0.34); a time window over the record graph (All|250|100|50 most recent by chrono) that drops nodes from the layout, taking the 500-node timeline from 87,078px wide to 17,478px; and hyperedge collapse to a single puck from the claim's panel, keeping members that another expanded claim still cites and suppressing the collapsed claim's blob. `tools/fixtures/large/` is a deterministic generator plus its output, checker-clean. One real bug found by the fixture and not by review: lane_layout assumed a parent is always placed before its child and raised KeyError when a child carried an earlier timestamp than its parent — a backdated import or skewed clock — which would have crashed the viz on a real adopted graph; such an edge now simply opens a new lane, with the matching guard on the pending-edge bookkeeping. Tests 143 -> 148, checker 0 violations.
