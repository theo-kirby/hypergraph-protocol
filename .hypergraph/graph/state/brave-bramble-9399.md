---
node_id: d42ae5a2-0cd3-53e1-8190-236a3721eea0
slug: brave-bramble-9399
title: Viz machinery
created_at: '2026-08-14T13:27:08+00:00'
parents:
- polished-pond-2718
summary: 'Superseded at 0.0.9: the page machinery left the repo with the viz cut; body kept as the record of how the page was built, what it cost, and the cache/perf lessons that transfer to a successor.'
flywheel:
  node_id: a186e182-d42d-5566-baad-44fe154b69df
  slug: soft-wave-9679
  revision: 1
  pushed_at: '2026-08-16T16:38:33+00:00'
  content_sha256: b8d051465d78ca673a3000a350f31540fdc800c45d15abdaaacadb059f8141b3
  parents_sha256: 8a5cac8569ae19b59da07c94ee132cf2455491411282f4f5f89fb128ce53eabb
  parents:
  - f4d676d8-a180-55fc-ae3f-54c1e4d3bcab
---
Status: superseded

## Current

**Superseded**: the machinery this node describes was removed from the repo at 0.0.9 — template, bundler, sources, browser baselines and viz fixtures all left with the viz cut, recoverable from git history at fbf18f2. The seam that replaces the page is described by the parent node, **Visualization** (`polished-pond-2718`) [rec: loyal-tide-3608]. What follows is the record of what the machinery was and what it cost, kept because the lessons transfer to any successor renderer.

- **Sources under `tools/viz/`** (an index.html skeleton, viz.css, fourteen JS parts and a manifest fixing their order) were concatenated into the `VIZ_TEMPLATE` constant by `tools/bundle_viz.py`; `viz --dev` read them straight off disk for the edit loop. Both hard properties were enforced by tests rather than by care: hypergraph.py stayed one copyable file, and the default page stayed self-contained [rec: southern-ivy-0706] [rec: tiny-stone-3934].
- **Blob geometry was excaligraph's signed distance field**, ported into `js/blob.js` (887 lines of TS → 562 of JS, MIT attribution kept): per-shape signed distances, an MST corridor with obstacle-aware routing, smooth-min union and smooth-max subtraction of every non-member, marching squares with the ambiguous-cell rule, Douglas-Peucker simplification [rec: smooth-wolf-8655] [rec: tiny-stone-3934].
- **The ~500-node scale target was met**: a synthetic 500-record/60-state fixture painted in 0.43s, down from 8.22s — a Barnes-Hut quadtree above 120 nodes, a grid hash replacing the 40-pass card de-overlap, level of detail by zoom, and hyperedge collapse to a single puck [rec: steady-haven-0365].
- **Two outputs deliberately broke the single-file property behind explicit flags**: `viz --format excaligraph` emitted a YAML spec for `excaligraph build`, verified end to end at 51 nodes / 57 edges / 12 hyperedges [rec: hollow-path-2087]; `viz --live` wrote a sibling data file the page polled [rec: cold-rose-6963].

## Negative knowledge

- [scope: optimising a graph page that draws implicit-surface blobs | confidence: high | evidence: steady-haven-0365] the asymptotically worst loop was not the bottleneck, and picking it by big-O would have bought 13% of the fix. At 500 nodes the O(n²) repulsion loop was worth 1.1s of 8.2 (Barnes-Hut alone: 8.22s → 7.11s) while the smooth-min distance field was 98% of the cost — the same page with blobs disabled painted in 0.14s. The measurement that settles it is building the page twice with one subsystem switched off, not reading the code.
- [scope: caching derived geometry in a graph page whose layout mutates node positions in place | confidence: high | evidence: tiny-stone-3934] a cache key built from the inputs you *think* moved silently misses a position change, because nothing in the key changes when a coordinate is written through. Three caches carried the same bug at once — the obstacle grid keyed on node count, the blob cache keyed on *member* positions only, and the repaint list restricted to a blob's own members — so a node dragged into a cluster was invisible to it three times over. The fix is one counter bumped by anything that moves a node, folded into every key; it also has to be *not* bumped by pan, zoom and toggles, or the caches stop working everywhere they used to.
- [scope: making a settled force layout "relax" | confidence: medium | evidence: tiny-stone-3934] reheating from a higher alpha than the layout ended at is a kick, not a settle. The full sim runs 240 ticks from alpha 1 and ends near 0.03; relaxing from 0.35 moved an already-settled drawing, and unanchored nodes drifted a few hundred px toward the origin over 90 ticks — the opposite of "keeps your drags". Relax has to start below where the sim landed and anchor what the user placed.
- [scope: a self-contained HTML page that polls a sibling data file | confidence: high | evidence: cold-rose-6963] live mode cannot work from `file://` — browsers block cross-file fetch — so the directory must be served over http. The failure is silent unless the page says so, which is why the indicator turns amber and polling stops after three failures.

## Provenance

- southern-ivy-0706 — sources split behind a build-time bundler; browser baselines captured
- smooth-wolf-8655 — excaligraph's distance-field blobs ported in, two-level cluster layout under them
- tiny-stone-3934 — drag-stable blobs over the posEpoch cache fix; eleven tuning sliders behind a viz: blob: block
- steady-haven-0365 — 500 nodes in 0.43s, and where the cost actually was
- hollow-path-2087 — the excaligraph spec export
- cold-rose-6963 — live mode
- wise-river-3571 — the Playwright harness and the seventh-phase coverage
- loyal-tide-3608 — the viz cut removed this machinery from the repo
