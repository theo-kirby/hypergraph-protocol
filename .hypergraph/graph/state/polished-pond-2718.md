---
node_id: f4d676d8-a180-55fc-ae3f-54c1e4d3bcab
slug: polished-pond-2718
title: Visualization
created_at: '2026-08-06T22:17:38.572359+00:00'
parents:
- cool-king-8586
summary: Four job-named views, each with a layout that fits its data; excaligraph's distance-field blobs ported in; focus-by-default cross-links; excalidraw and live outputs; 500 nodes in 0.43s.
flywheel:
  node_id: f4d676d8-a180-55fc-ae3f-54c1e4d3bcab
  slug: polished-pond-2718
  revision: 2
  pushed_at: '2026-08-07T18:12:06.426139+00:00'
  content_sha256: a22c1dd604fdf9f740074c81670873773792530ace33a8b0c0809c0f8cba220f
---
Status: working

## Current

- `viz` emits a self-contained interactive page with **four views, each named after the question it answers and each with a layout that fits the shape of its data**: Timeline (record graph as `git log --graph` lanes, time along x), Frontier (state graph as a status board), Provenance (both graphs side by side), Clusters (each claim's record set as a blob). The pre-rename deep links `#record`/`#state`/`#combo`/`#combination`/`#hyper` still resolve [rec: gilded-pebble-5687] [rec: southern-ivy-0706] [rec: rough-moss-4912].
- **The overhaul was driven by measurement, not taste.** One generic Sugiyama layout drove all four views, and on this repo's own graph three of the four fitted below 0.29 zoom, where nothing is legible. Measured on a frozen 39-record/12-state fixture, fit zoom went 0.183 → 1.0 (Timeline), 0.283 → 1.0 (Frontier), 0.208 → 1.057 (Provenance), and Clusters gained labels it never had [rec: southern-ivy-0706] [rec: rough-moss-4912] [rec: wise-river-3571].
- **Fitting is axis-aware, with a floor of 0.45.** A timeline fits its height and scrolls through history; boards and columns fit their width and scroll down. A floor alone was not enough — at 0.45 an 11.5px label renders at 5px — so the choice of axis is what actually made the views readable [rec: rough-moss-4912].
- **Lanes come from the record graph's real parent relation.** `lane_layout()` assigns a `git log` lane per node in time order, tracking per lane how many nodes still owe an edge; 39 nodes resolve to 3 lanes, 500 to 7 [rec: rough-moss-4912] [rec: steady-haven-0365].
- **Hyperedge blobs are a signed distance field**, ported from excaligraph (MIT, attributed in `js/blob.js`): per-member outline, a corridor along a minimum spanning tree, smooth-minimum merging, and non-members subtracted so the boundary bends around whatever is in the way. A convex hull swallows every non-member between three far-apart members, which is a false picture, so the hull survives only as the fast fallback while dragging and below a zoom threshold. Under it, a two-level force layout places hyperedges as bodies before nodes settle, because a flat simulation cannot express "these belong together" [rec: smooth-wolf-8655].
- **Cross-graph links have a mode — focus (default) | all | none.** 177 links over 51 nodes is a hairball however it is drawn, and the density is genuine (86 of 89 provenance links are declared, so filtering would hide structure). Provenance therefore opens with zero cross-links and draws only what you select or hover; `all` bundles them into one ribbon per claim through a staggered spine. Ordering the state column by the barycentre of the record work each claim cites cuts crossings 4146 → 3599, a real but modest 13% [rec: vast-sage-0617].
- **`viz --format excaligraph`** emits a spec that `excaligraph build` turns into a hand-editable Excalidraw scene — verified end to end (51 nodes, 57 edges, 12 hyperedge blobs; every node keeps a `link:` to its markdown source). The status palette is restated in Python as `PALETTE` and a test asserts it still matches the page, so a figure and the page cannot silently disagree [rec: hollow-path-2087].
- **`viz --live`** writes a sibling `viz.data.json` the page polls, pulsing nodes that appeared since the last poll. It is the one output that deliberately breaks self-containment, so it is a flag; without it not a byte of network code runs. It cannot work from `file://` — browsers block cross-file fetch — and the page says so rather than failing silently [rec: cold-rose-6963].
- **The ~500-node target is met: 0.43s first paint, down from 8.22s**, with the small-graph output unchanged. Barnes-Hut above 120 nodes, grid hashes for card de-overlap and blob avoidance, tile-pruned blob sampling under a render-wide budget, level of detail by zoom, a time window over the record graph (87,078px of timeline → 17,478px), and hyperedge collapse to a puck [rec: steady-haven-0365].
- **Both hard properties held throughout and are now enforced by tests rather than by care**: `tools/hypergraph.py` is still one copyable file, and the default page still fetches nothing. The page is authored under `tools/viz/` (html skeleton + css + 12 JS parts + manifest) and bundled into the `VIZ_TEMPLATE` constant by `tools/bundle_viz.py`; `assemble_viz_template()` lives in the shipped file and the bundler imports it, so `viz --dev` and the constant cannot drift [rec: southern-ivy-0706].
- **Layout is deterministic everywhere** — no `Math.random`, jitter is a hash of the slug — and two loads of one input produce byte-identical blob SVG (151,059 characters compared directly). A Playwright harness (dev group only, self-skipping) measures every view in chromium against frozen fixtures, so a layout regression fails a test [rec: southern-ivy-0706] [rec: smooth-wolf-8655].
- **Still open: the viz has never rendered anything but this project's own graph.** The benchmark thrust's nine-run dataset exists and is named as the first external subject, and remains unrendered [rec: ancient-dew-4488] [rec: southern-ridge-1802].

## Negative knowledge

- [scope: optimising this visualization | confidence: high | evidence: steady-haven-0365] the O(n²) repulsion loop is not the bottleneck at 500 nodes. It was named as the suspect and cost 1.1s of an 8.2s first paint; the blob distance field was 98% of it — the same page with blobs disabled painted in 0.14s. Attribute cost by measurement before optimising, even when the quadratic loop is right there.
- [scope: fitting a graph view to a window | confidence: high | evidence: rough-moss-4912] a minimum-zoom floor alone does not make a view readable. At 0.45 an 11.5px label renders at 5px, so "nothing fits below 0.45" and "every label is readable" are contradictory for any long strip. Fitting must pick an axis and let the other one scroll.
- [scope: exporting figures from a graph tool | confidence: high | evidence: hollow-path-2087] "the build and preview commands succeed" is not a legibility criterion. The first excaligraph export built and rendered cleanly and was useless — 234 edges carrying paragraph-length impact deltas render as a mat of orange text over the graph.
- [scope: laying out a record graph in lanes | confidence: high | evidence: rough-moss-4912, steady-haven-0365] two traps, both found by testing rather than review. Freeing a lane when its *tip* has no unplaced children loses the column of a parent that still owes an edge to a later child, and routes that edge through intervening nodes; and a child can carry an earlier timestamp than its parent (backdated import, skewed clock), so the parent may have no lane yet when the child is placed.

## Provenance

- long-tree-4179 — stack comparison decision, original three-view viz, tests, screenshot verification
- morning-rain-7488 — force-directed hyperedge-blob view; the hyperedge machinery the current one still builds on
- still-forest-9161 — tabs collapsed into the toggle-driven view with presets; chrome redesign
- southern-ridge-1802 — Operator directive requesting viz improvements; benchmark data named as the first dataset
- ancient-dew-4488 — the benchmark dataset lands and is named the first real external subject
- gilded-pebble-5687 — decision: seven-phase overhaul, four job-named views, excaligraph geometry, source split
- southern-ivy-0706 — phase 0: source split behind a bundler, view rename, browser baselines quantifying the defect
- rough-moss-4912 — phase 1: git-log lanes, the frontier board, axis-aware fitting and the zoom floor
- smooth-wolf-8655 — phase 2: excaligraph's distance field ported in; two-level cluster layout under it
- vast-sage-0617 — phase 3: cross-link focus/all/none, spine bundling, barycentre-ordered state column
- hollow-path-2087 — phase 4: excaligraph spec export, palette agreement test, the unreadable first figure
- cold-rose-6963 — phase 5: live mode and the file:// constraint
- steady-haven-0365 — phase 6: 500 nodes in 0.43s; measured attribution; the lane-layout crash
- wise-river-3571 — phase 7: legend, keyboard, dark theme, export across all four layouts
