---
node_id: 711d25df-9758-5c59-bf94-e7d04486dabd
slug: rough-moss-4912
title: 'Viz phase 1: git-log lanes for the record graph, a status board for the state graph, axis-aware fitting'
created_at: '2026-08-09T09:41:55+00:00'
parents:
- southern-ivy-0706
summary: 'Two layouts that fit their data, plus axis-aware fitting with a zoom floor: every view now opens at or above 0.9 instead of 0.18-0.28.'
---
## What

Replaced the two layouts that could not serve their data. The record graph now
draws as `git log --graph` lanes with time on x, and the state graph draws as a
status board with a tree toggle. Added a zoom floor and made fitting axis-aware,
which is what actually made the views legible. Wrapped the bundled page in an
IIFE, the one piece of the target structure Phase 0 had to defer.

## Why

Follows `southern-ivy-0706`, whose baseline put numbers on the defect: fit zoom
0.183 for the record view and 0.283 for the state view. Both numbers came from
the same mistake — one generic Sugiyama layout applied to two graphs that are not
shaped like a DAG to be ranked. The record graph is a timeline (29 layers deep, 3
wide). The state graph is a status board (12 nodes, depth 2).

## Method

**Payload** (`build_viz_data`, extended not replaced). Record nodes gained
`chrono` (dense rank over real creation order) and `lane`. State nodes gained
`prov_count`, `last_record_at` (newest record node cited as provenance) and
`impact_count`. `layer`/`order`/`seq` stayed, because the tree toggle and the
Provenance view still use `layered_layout` and `state_dfs_order`.

**`lane_layout()`** assigns lanes chronologically: a node continues its earliest
parent's lane when that lane's *tip* is that parent, otherwise it opens the lowest
lane with no edge pending through it.

The pending-edge bookkeeping is the load-bearing part, and the first version got
it wrong. Freeing a lane when its *tip* had no unplaced children left looks
right and is not: a parent whose lane was taken over by its first child still owes
an edge to its second, and that edge then gets drawn straight through whatever
chips sit between them. The fix tracks, per lane, how many nodes in it still owe
an edge. `test_lane_layout_keeps_a_shared_lane_adjacent` checks the resulting
property on this repo's real graph — if a node shares a lane with a parent, that
parent is its immediate lane-neighbour — and it fails on the first version.

**Timeline** (`js/layout-timeline.js`): x from `chrono` in `rank` mode, or from
real dates in `time` mode with per-gap clamping to [0.35, 3] rank steps so a
three-week idle gap does not push the next month off screen. Chips are 158x26 with
the title truncated to 24 characters; the rest of the node is one click away, which
is the trade that keeps 39 of them legible side by side. Behind them: a lane rule
and label per lane, a dashed date tick at each new calendar day, and the
high-water mark as a purple rule with the unreconciled tail tinted amber.

**Frontier board** (`js/layout-board.js`): columns broken | blocked | open |
working | superseded, frontier first, ordered within a column by `last_record_at`
descending. Cards carry title, slug, status dot, provenance count and last-touched
date. An empty column collapses to a 52px rail with a rotated header rather than
disappearing — "nothing is broken" is a real answer, and keeping five full columns
would have cost 1290px of width for two that hold anything. The Tree toggle
switches to the indented architecture list that mirrors STATE.md.

**Fitting**, which turned out to matter more than either layout. A zoom floor
alone was not enough: at 0.45 an 11.5px label renders at 5px, so "no view fits
below 0.45" and "every label is readable" are contradictory for a 6864px strip.
`fitPlan()` therefore picks an axis — a timeline fits its *height* and scrolls
through history; boards and columns fit their *width* and scroll down the list —
capped at 1.0 for the two layouts designed at 1:1. Layout scenery counts as
content in `worldBounds()`, so the empty `broken` rail is not cropped just because
it holds no cards.

Node shape now follows the layout (`styleFor`/`dimsFor`), not only the Nodes
toggle, and `edgePath`/`worldBounds`/`blobPath` were generalised from the hardcoded
card size to per-node dimensions. Timeline parent edges leave the parent's right
edge and enter the child's left edge with the bend held near the child, so a lane
change reads as a hook.

## Result

Fit zoom and world box per view, same fixture and viewport as the Phase-0
baseline:

| view | before | after |
| --- | --- | --- |
| Timeline | 0.183 · 847 x 4121 | **1.0** · 6864 x 197 |
| Frontier | 0.283 · 3295 x 201 | **1.0** · 716 x 946 |
| Provenance | 0.208 · 1028 x 3600 | **1.057** · 1028 x 3602 |
| Clusters | 0.877 · 480 x 805 | 0.9 · 480 x 805 |

Every view now opens at or above 0.9, against a floor of 0.45 —
`test_no_view_fits_below_the_zoom_floor` asserts it. The record graph resolves to
**3 lanes over 39 nodes** (14 / 24 / 1), which is the "~3–4 lanes" the plan
predicted. Provenance moved from 0.208 to 1.057 purely from the axis-aware fit; it
is legible now and still a hairball, which is Phase 3's job.

Tests: 130 pass (was 123; +7 — three lane-layout properties, the new payload
fields, the zoom floor, the two layout-local toggles, and control visibility).
Checker: 0 violations.

One deviation from the plan, driven by the data. The plan asks for "a vertical
rule at each high-water-mark advance"; the export carries only the *current* high-
water mark, and past values are nowhere in either graph, so there is nothing to
draw a history from. What ships is one rule at the current mark plus an amber tint
over the unreconciled tail — the same question answered with the data that exists.
Recovering the advance history would need reconcile to record its previous mark,
which is a protocol change and out of scope here.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: hg-viz
- commit: 33e7c29eaf6383cbb5292ba3d35871632273414d

## State Impact

- target: polished-pond-2718 — the two unreadable views are fixed, and the fix was as much about fitting as about layout. Record graph now draws as `git log --graph` lanes (new `lane_layout()` in hypergraph.py; payload gains `chrono` + `lane`) with x from rank or from real dates with clamped gaps, compact 158x26 chips, a lane ruler, a date gutter, and the high-water mark as a rule with the unreconciled tail tinted. State graph draws as a status board (broken|blocked|open|working|superseded, frontier first, freshest first within a column, cards carrying prov_count and last_record_at from the extended payload) with empty columns collapsed to labelled rails and an architecture-tree toggle mirroring STATE.md. Measured on the frozen self fixture, fit zoom went 0.183 -> 1.0 (Timeline), 0.283 -> 1.0 (Frontier), 0.208 -> 1.057 (Provenance); the record graph resolves to 3 lanes over 39 nodes. A zoom floor of 0.45 alone was NOT sufficient — at 0.45 an 11.5px label renders at 5px — so fitting became axis-aware: timelines fit height and scroll through time, boards and columns fit width and scroll down, both capped at 1:1. Node shape now follows the layout rather than the Nodes toggle, and edge/bounds/blob geometry was generalised off the hardcoded card size. One defect found and fixed during the work: the first lane rule freed a lane when its tip had no unplaced children, which loses the column of a parent that still owes an edge to a later child and routes that edge through intervening chips; per-lane pending-edge counting fixes it and a property test on the real graph guards it. One plan deviation: "a vertical rule at each high-water-mark advance" is not implementable — the export carries only the current mark and past values are recorded nowhere, so one rule plus the unreconciled band ships instead. Tests 123 -> 130, checker 0 violations.
