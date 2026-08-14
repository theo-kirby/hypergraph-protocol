---
node_id: 82e9ac9c-2590-5cdd-803e-9b978ef2e7da
slug: smooth-wolf-8655
title: 'Viz phase 2: excaligraph''s distance-field blobs ported in, two-level cluster layout under them'
created_at: '2026-08-09T09:49:57+00:00'
parents:
- rough-moss-4912
summary: Convex hulls replaced by a ported signed-distance field with corridors and non-member avoidance; a two-level force layout separates the 12 hyperedges.
flywheel:
  node_id: cd6eaad8-b7c0-5ef4-8343-3b17c4bade62
  slug: white-dust-6761
  revision: 0
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: aefdfe5c21e864ba2f22eabc43a2ed26a012b1ce287b40315090e3e2ff48cddf
  parents_sha256: 876f3f7dad1c58558a7ddd69d857bd6cf8685222130fbd55333fa45e05ad4ed6
  parents:
  - 5ec9b91e-eda8-5d52-80e1-dc5db30f5cab
---
## What

Ported excaligraph's signed-distance-field blob geometry into the page, replaced
the flat force simulation under it with a two-level one that lays out hyperedges
before nodes, labelled the circle style, and moved blob labels onto the outline
they belong to.

## Why

Follows `rough-moss-4912`. Phase 1 left Clusters as the one view whose *fit* was
fine and whose *content* was not: 12 convex hulls over 39 unlabelled circles,
overlapping into a single pile. Two separate defects, and fixing either alone
would not have helped.

A convex hull is the wrong primitive for set membership. The hull of three
far-apart members swallows every non-member between them, so the picture asserts
things that are not true. `~/excaligraph/src/geometry/blob.ts` (MIT) already
solves this properly and is already deterministic, which matches this page's
no-`Math.random` rule.

The layout was the other half. A flat sim repels every node from every other
equally, so it has no way to express "these fourteen belong together" — group
separation has to be decided by a level that knows about groups.

## Method

**The port**: 887 lines of TypeScript to 562 lines of JavaScript, MIT attribution
kept at the top of `js/blob.js`, without the URL — this page must fetch nothing,
and `test_render_viz_emits_selfcontained_html` asserts there is no `https://` in
the output. Everything the field needs came across: per-shape signed distances
(rectangle and ellipse), the minimum-spanning-tree corridor with obstacle-aware
routing, polynomial smooth-min union and smooth-max subtraction, marching squares
with the ambiguous-cell rule, Ramer-Douglas-Peucker simplification, even-odd hole
rejection, and canonical member ordering (a smooth minimum is not associative, so
a hyperedge is sorted before it is folded or its blob would depend on member
order). Corner filleting was left out: at resolution 5 the traced contour is
already smooth, and it is drawn as a closed Catmull-Rom curve.

The hull stays as the fast fallback, as planned, on two triggers: while a node is
being dragged, and below `BLOB_FIELD_MIN_ZOOM`. Crossing either boundary redraws
just the blob layer. Field results are cached per hyperedge, keyed by the rounded
member positions.

**Two-level force** (`js/layout-force.js`). First the twelve hyperedges are laid
out as a coarse graph: each is a body with radius `40 + 26*sqrt(members)`, pushed
apart until they clear each other by 34px, pulled together in proportion to
shared members, seeded on a ring largest-first so the big clusters claim space
first. Then nodes settle, held toward the centre of their hyperedge — weight 0.22
for a node in one cluster, 0.10 for a node in several, so a shared node can sit
in the overlap instead of fighting. Members seed on a sunflower spiral inside
their cluster (even area coverage) rather than one wide ring, which was stringing
big clusters out into chains. Parent-edge springs were weakened from 0.03 to
0.012: in this view the grouping is the message, and a strong causal chain drags
members out of their blob.

**Labels.** The circle style is labelled now. Labels are drawn always and shown
by zoom in `applyTf` (threshold 0.62), so panning stays cheap. Blob labels are
placed *on* the outline — excaligraph's top | bottom | centre idea — each taking
the first anchor that does not collide with one already placed, instead of being
pushed up off the canvas by the old de-overlap loop.

## Result

Clusters now draws **12 distinguishable blobs** with visible corridors, bending
around non-members, over 39 labelled circles. Fit zoom 0.793 (was 0.877 with
hulls; the layout is larger because the groups are actually separated). Load and
first render of the view: **0.34s**.

Determinism holds through the whole port: two loads of the same input produce
**byte-identical blob SVG** — 151,059 characters of path data, compared directly
in `test_clusters_draws_distinguishable_labelled_blobs`. The same test asserts
the outlines contain more than 200 cubic segments, which a hull could not, so a
silent fallback to the hull would fail rather than merely look worse.
`test_blob_labels_do_not_collide` checks all 66 label pairs for overlap.

**One real bug, found by writing the avoidance and not seeing it work.** The
non-member list was read from `nodeEls`, but `renderAll` builds the blob layer
*before* the node layer — so on the first render `nodeEls` is empty and on later
ones it holds the previous render's nodes. Avoidance was silently disabled
exactly when it mattered most, and the blobs still looked plausible, which is
what made it worth recording. The avoid list now comes from the position map,
which is the layout's own output and cannot be stale.

Tests: 133 pass (was 130; +3 — the ported-symbol and attribution guard, the
cluster/blob acceptance test, the label-collision test). Checker: 0 violations.

Not done, deliberately: node labels in dense regions still overlap each other.
Fixing that needs the grid-hash de-overlap that Phase 6 brings for exactly this
reason, and doing it twice would be waste.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: hg-viz
- commit: 52351283432899b9b2d089715ac195dbebba09a5

## State Impact

- target: polished-pond-2718 — the Clusters view is rebuilt on excaligraph's blob mathematics and a layout that can express groups. `js/blob.js` ports the signed-distance field from excaligraph's src/geometry/blob.ts (887 lines TS -> 562 lines JS, MIT attribution kept, URL deliberately omitted so the page stays self-contained): per-shape signed distances, an MST corridor with obstacle-aware routing, smooth-min union and smooth-max subtraction of every non-member, marching squares with the ambiguous-cell rule, Douglas-Peucker simplification, even-odd hole rejection, canonical member ordering. Corner filleting was dropped as unnecessary at resolution 5. The convex hull survives as the fast fallback below a zoom threshold and while dragging. Under it, the flat force sim was replaced by a two-level one: hyperedges are laid out first as twelve bodies with size-derived radii, pushed apart and pulled together by shared membership, then nodes settle toward their cluster centre (weight 0.22 single-cluster, 0.10 shared) from a sunflower seed. The circle style is labelled now, shown by zoom threshold. Blob labels sit on the outline (top|bottom|centre anchors) instead of being pushed up off the canvas. Result: 12 distinguishable blobs with corridors over 39 labelled circles, 0.34s to load and render, and byte-identical blob SVG across two loads (151,059 characters compared directly) — determinism survived the port. One defect found and fixed: the non-member avoidance list was read from `nodeEls`, which renderAll populates *after* the blob layer, so avoidance was silently disabled on first render while still looking plausible; it now reads the layout's own position map. Node-to-node label overlap in dense regions is knowingly left to Phase 6, which brings the grid-hash de-overlap. Tests 130 -> 133, checker 0 violations.
