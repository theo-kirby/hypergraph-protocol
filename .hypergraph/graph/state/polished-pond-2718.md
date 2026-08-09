---
node_id: f4d676d8-a180-55fc-ae3f-54c1e4d3bcab
slug: polished-pond-2718
title: Visualization
created_at: '2026-08-06T22:17:38.572359+00:00'
parents:
- cool-king-8586
summary: Four job-named views (Timeline/Frontier/Provenance/Clusters) each with a fitting layout; excaligraph's distance-field blobs ported in, an excalidraw spec export, live mode, and 500 nodes in 0.43s.
flywheel:
  node_id: f4d676d8-a180-55fc-ae3f-54c1e4d3bcab
  slug: polished-pond-2718
  revision: 3
  pushed_at: '2026-08-09T10:15:16+00:00'
  content_sha256: 79b42c3cb03589863b6a3a68378d8332a6bec3a5ded1aae9ae2f823c6533b129
---
Status: working

## Current

- `tools/hypergraph.py viz` emits a self-contained interactive HTML page with four views named after the job each does: **Timeline** (the record graph as `git log --graph` lanes, x by rank or by real dates with clamped gaps, a lane ruler and date gutter, the high-water mark as a rule with the unreconciled tail tinted), **Frontier** (the state graph as a status board — broken|blocked|open|working|superseded, frontier columns first, empty columns kept as labelled rails, with an architecture-tree toggle mirroring STATE.md), **Provenance** (both graphs in columns), and **Clusters** (each claim's record set as a distance-field blob) [rec: rough-moss-4912] [rec: smooth-wolf-8655] [rec: vast-sage-0617]. This supersedes the earlier toggle-driven single view with presets Record/State/Columns/Force, which drove all four arrangements from one generic Sugiyama layout [rec: long-tree-4179] [rec: morning-rain-7488] [rec: still-forest-9161]; the pre-rename hashes #record/#state/#combo/#combination/#hyper still deep-link to the matching view, and #<slug> still jumps to a node [rec: southern-ivy-0706].
- The overhaul was driven by a measured defect and closed against the same measurements. Fit zoom went 0.183 → 1.0 (Timeline), 0.283 → 1.0 (Frontier), 0.208 with 234 edges drawn → 1.057 with zero cross-links until asked (Provenance), and 0.877 with 12 unlabelled convex hulls → 0.918 with 12 distance-field blobs and 39 labels (Clusters), on a frozen 39-record/12-state snapshot of this repo's own graph [rec: gilded-pebble-5687] [rec: southern-ivy-0706] [rec: wise-river-3571].
- Cross-graph links carry a mode — focus (default) | all | none — orthogonal to the per-kind checkboxes: the checkboxes say which kinds may draw, the mode says how many. Focus draws only the selected *or hovered* node's links, so Provenance opens with zero of 177; `all` routes each claim's links through a staggered vertical spine as bundled ribbons without arrowheads. The state column is ordered by the mean `chrono` of the record work each claim cites [rec: vast-sage-0617].
- Blob geometry is excaligraph's signed distance field ported into `js/blob.js` (887 lines TS → 562 lines JS, MIT attribution kept, URL deliberately omitted so the page fetches nothing): per-shape signed distances, an MST corridor with obstacle-aware routing, smooth-min union and smooth-max subtraction of every non-member, marching squares with the ambiguous-cell rule, Douglas-Peucker simplification. The convex hull survives as the fast fallback below a zoom threshold and while dragging. Under it, a two-level force sim lays out the twelve hyperedges as bodies first, then settles nodes toward their cluster centre [rec: smooth-wolf-8655].
- The ~500-node scale target is met: a synthetic 500-record/60-state fixture paints in 0.43s, down from 8.22s, with the small-graph baseline unchanged, so none of it was a visible trade. Landed alongside: a Barnes-Hut quadtree above 120 nodes with the exact loop kept below as both the cheaper path and the reference, a grid hash replacing the 40-pass card de-overlap and the blob avoidance scan, level of detail by zoom, a time window over the record graph (All|250|100|50 by `chrono`), and hyperedge collapse to a single puck [rec: steady-haven-0365].
- `viz --format excaligraph` emits a YAML spec that `excaligraph build` turns into a hand-editable Excalidraw scene, verified end to end against this repo's graph with excaligraph's real CLI: 51 nodes / 57 edges / 12 hyperedges, every node keeping a `link:` back to its markdown source, layout dagre LR, seed derived from the project name so a regenerated figure keeps its jitter. The status palette is restated in Python as `PALETTE` with a test asserting every value still appears in the bundled page, so figures and the page cannot silently disagree on what "broken" looks like. Two-step by design — nothing in hypergraph.py shells out and node stays optional [rec: hollow-path-2087].
- `viz --live` writes the page alongside a sibling `viz.data.json`, polls it on an interval, and redraws with a SMIL pulse ring around every node that appeared since the last poll; on a change every derived cache is dropped, because a cache that survives a data swap is a drawing that looks live and is not. It is the one output that deliberately breaks the single-file property, so it is an explicit flag, and `js/live.js` executes no network code at all unless the flag set `DATA.live` [rec: cold-rose-6963].
- The viz sources live under `tools/viz/` (an index.html skeleton, viz.css, thirteen JS parts and a manifest fixing their order) and are concatenated into the `VIZ_TEMPLATE` constant by `tools/bundle_viz.py`; `viz --dev` reads them straight off disk for the edit loop, and `assemble_viz_template()` lives in hypergraph.py so the dev path and the constant cannot drift. Both hard properties are now enforced by tests rather than by care: hypergraph.py stays one copyable file, and the default page stays self-contained [rec: southern-ivy-0706]. Coverage went 117 → 151 tests over the seven phases, including a Playwright harness (dev group only, self-skipping) that measures every view in chromium against the frozen fixture and asserts first paint on the 500-node fixture [rec: wise-river-3571].
- The benchmark dataset now exists and is the first real external subject for this work: 9 runs x (fidelity by section, cold-start timings, per-turn token/tool traces) in `research/runs/main/analysis.json`, with the raw session transcripts harvested alongside [rec: ancient-dew-4488]. It is first-run data from a harness later found to be uncontrolled (protocol-benchmark-4417), so it is a rendering subject, not a source of claims [rec: staid-field-2723]. Rendering it is the open work: every view so far has been measured on the project's own graph [rec: southern-ridge-1802].

## Negative knowledge

- [scope: optimising a graph page that draws implicit-surface blobs | confidence: high | evidence: steady-haven-0365] the asymptotically worst loop was not the bottleneck, and picking it by big-O would have bought 13% of the fix. At 500 nodes the O(n²) repulsion loop was worth 1.1s of 8.2 (Barnes-Hut alone: 8.22s → 7.11s) while the smooth-min distance field was 98% of the cost — the same page with blobs disabled painted in 0.14s. The measurement that settles it is building the page twice with one subsystem switched off, not reading the code.
- [scope: fit-to-window in a graph viewer | confidence: high | evidence: rough-moss-4912] a zoom floor does not make a view readable, it only stops it disappearing: at the 0.45 floor an 11.5px label renders at 5px. Fitting has to be axis-aware — a timeline fits height and scrolls through time, a board or column view fits width and scrolls down, both capped at 1:1 — and a view that still does not fit must scroll rather than shrink.
- [scope: reducing crossings in a dense bipartite provenance view | confidence: high | evidence: vast-sage-0617] barycentre ordering has a low ceiling when the links are genuinely dense: 4146 inverted pairs in architecture order → 3599 in barycentre order, −13.2%, with median ordering worse (3673). Ordering is not the lever when 86 of 89 provenance links are *declared* rather than incidental; drawing fewer links is.
- [scope: drawing reconciliation history from a graph export | confidence: high | evidence: rough-moss-4912] past high-water marks are not recoverable — the export carries only the current one and previous values are recorded nowhere — so a timeline can mark where the frontier is now, not where it has been.
- [scope: accepting a generated figure | confidence: high | evidence: hollow-path-2087] "the build and the preview both succeed" is not a legibility test and passed on a figure that was useless: 234 edges carrying paragraph-length impact deltas render as a mat of text over the graph. An acceptance criterion for a figure has to name what must be readable in it.
- [scope: a self-contained HTML page that polls a sibling data file | confidence: high | evidence: cold-rose-6963] live mode cannot work from `file://` — browsers block cross-file fetch — so the directory must be served over http. The failure is silent unless the page says so, which is why the indicator turns amber and polling stops after three failures.

## Provenance

- long-tree-4179 — stack comparison decision, original three-view viz, tests, screenshot verification
- morning-rain-7488 — force-directed hyperedge-blob view; hyperedges/hull/blob machinery the unified view built on
- still-forest-9161 — tabs collapsed into the unified toggle-driven view with presets; chrome redesign
- southern-ridge-1802 — Operator directive requesting viz improvements; benchmark data named as the first dataset
- ancient-dew-4488 — the nine-run dataset lands as the first external subject
- staid-field-2723 — that dataset qualified: renderable, but not a source of claims
- gilded-pebble-5687 — decision: the seven-phase overhaul, its measured motivation, and the source split
- southern-ivy-0706 — phase 0: sources split behind a build-time bundler, views renamed, browser baselines captured
- rough-moss-4912 — phase 1: git-log lanes, the status board, axis-aware fitting
- smooth-wolf-8655 — phase 2: excaligraph's distance-field blobs ported in, two-level cluster layout under them
- vast-sage-0617 — phase 3: link modes, the bundled spine, barycentre-ordered state column
- hollow-path-2087 — phase 4: the excaligraph spec export
- cold-rose-6963 — phase 5: live mode
- steady-haven-0365 — phase 6: 500 nodes in 0.43s, and where the cost actually was
- wise-river-3571 — phase 7: legend, keyboard, dark theme, export across all four views
