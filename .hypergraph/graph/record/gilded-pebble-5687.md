---
node_id: fec39436-0053-5c55-b47a-40080584f38c
slug: gilded-pebble-5687
title: 'Decision: viz overhaul — four job-named views, excaligraph blob geometry, source split'
created_at: '2026-08-09T09:18:09+00:00'
parents:
- ancient-dew-4488
summary: 'Forward-work decision: replace one generic Sugiyama layout with four job-named views, port excaligraph''s SDF blob geometry, split the viz sources behind a bundler.'
---
## What

Set a new direction for the visualization work, before any of it is built: a
seven-phase overhaul of `tools/hypergraph.py viz`. The current page is one generic
Sugiyama layout driving four views. Three of the four views are unreadable on this
repo's own graph. The decision is to replace the single layout with four
job-named views, each with a layout that fits the data's real shape, to port
excaligraph's signed-distance-field blob geometry into the page, and to split the
viz sources out of the single-file script while keeping the single-file property.

## Why

Follows `ancient-dew-4488`, which recorded the benchmark dataset as the first real
external subject for the visualization work. Measuring the current page against
this repo's own graph (38 record nodes, 12 state nodes, 176 cross-links) shows
that the generic layout is the defect, not the styling:

- **Record view**: the record graph is 29 layers deep with a widest layer of 3.
  Sugiyama renders it as a 1:15 ribbon; fit-to-window zooms to ~15% and nothing is
  legible. The record graph is a *timeline*, not a DAG to be ranked.
- **State view**: 12 nodes, depth 2 — a flat bar in an empty screen. It holds the
  frontier, which is the thing an arriving agent needs most. It is a *status
  board*, not a graph.
- **Columns view**: 89 provenance + 87 impact links drawn at once is a hairball.
- **Force view**: 12 hyperedges with sizes 14…1, drawn as convex hulls, overlap
  into mush with colliding labels.

Two candidate explanations were checked and ruled out. **Link filtering will not
help**: 86 of the 89 provenance links are *declared* in `## Provenance` sections;
only 6 are incidental, so the density is genuine and hiding it would hide real
structure. **The depth is not an artefact of the export**: the record graph really
is a near-linear causal chain, which is what a well-kept record graph looks like.

`~/excaligraph` (MIT) solves the blob half properly. `src/geometry/blob.ts` is a
signed distance field: per-member outline, a corridor along a minimum spanning
tree, smooth-minimum merge, and non-members pushing the outline away — not a
convex hull. It is already deterministic, which matches this page's no-`Math.random`
rule.

## Method

No implementation yet. This node records the decision and its constraints so the
frontier carries the gap (SPEC: Forward work).

**Decisions taken:**

- Audience is four-way: personal review, agent orientation, public figures, live
  status. Agents keep reading `STATE.md` — no agent-facing work lands inside the viz.
- Excaligraph is used *twice*: its blob mathematics is ported into the page, and
  `viz --format excaligraph` emits a YAML spec that `excaligraph build` consumes.
  Node stays optional and out of the core path; nothing in `tools/hypergraph.py`
  shells out.
- The four views are renamed after the job they do — Timeline, Frontier,
  Provenance, Clusters — with the old deep-link hashes kept as aliases.
- State view is a board by default, with the architecture tree as a toggle.
- Scale target is ~500 nodes.

**Hard constraints that shape the split.** `tools/hypergraph.py` carries a
`#!/usr/bin/env -S uv run --quiet` shebang and a PEP 723 header, and
`pyproject.toml` force-includes it as the single module `hypergraph_protocol.py`.
So the script must stay one copyable file, the emitted HTML must stay
self-contained (no network, no external asset), and `tests/test_packaging.py`'s
allow-list must keep passing. The resolution is to split the *sources* under
`tools/viz/`, bundle them into the `VIZ_TEMPLATE` constant at build time with
`tools/bundle_viz.py`, and guard the bundle with a `test_viz_bundle_in_sync` test
so editing JS without rebundling fails CI rather than shipping stale output.

**Phases:** 0 foundation (source split, bundler, Playwright baselines, view
rename) · 1 the two broken layouts (git-log lane timeline, frontier board, a
global zoom floor) · 2 the blob port and cluster cohesion · 3 provenance link
modes plus edge bundling · 4 `.excalidraw` export · 5 live mode · 6 scale to 500
nodes (Barnes-Hut, grid hash, level of detail) · 7 polish and land.

**Acceptance criteria are set per phase**, the load-bearing ones being: Phase 0
output byte-identical to today's; Phase 1 every chip and card readable at default
zoom with no view fitting below 0.45 scale; Phase 2 twelve distinguishable blobs
and two renders of one input giving identical SVG; Phase 3 zero cross-links drawn
until a node is selected; Phase 6 a 500-node fixture painting in under ~1.5s. At
every phase `test_render_viz_emits_selfcontained_html` must still pass.

## Result

No work done yet — this is a forward-work decision node. The gap it opens is that
`polished-pond-2718` currently claims a working visualization, and that claim is
true only mechanically: the page renders, and three of its four views cannot be
read. Reconcile should carry that qualification onto the state node so a fresh
agent is not misled by "Visualization — working".

The risk accepted here is scope: seven phases is a large commitment against a
component that already renders. It is taken because the visualization is the
project's public face, and because the benchmark dataset from `ancient-dew-4488`
gives it a real external subject for the first time.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: hg-viz
- commit: 3276bd9f651c0ff163c229a31c3e5db4ea74c113

## State Impact

- target: polished-pond-2718 — direction set for a seven-phase viz overhaul, no work done yet. Qualifies the existing "working" claim: the page renders and is well styled, but one generic Sugiyama layout drives all four views and three of the four are unreadable on this repo's own graph (record graph is 29 layers deep with a widest layer of 3, so fit-to-window lands at ~15%; state view is 12 nodes at depth 2 in an empty screen; Columns draws 176 cross-links as a hairball; Force overlaps 12 convex hulls into mush). Link filtering was checked and ruled out — 86 of 89 provenance links are declared in `## Provenance` sections, so the density is genuine. Plan: four job-named views (Timeline/Frontier/Provenance/Clusters) each with a fitting layout, excaligraph's signed-distance-field blob geometry ported into the page (MIT, attributed) plus a `viz --format excaligraph` YAML export, live mode behind an explicit flag, and a ~500-node scale target. Sources split under `tools/viz/` and bundled into `VIZ_TEMPLATE` by `tools/bundle_viz.py`, preserving both the single-file script property and the self-contained HTML output, with a bundle-sync test as the guard.
