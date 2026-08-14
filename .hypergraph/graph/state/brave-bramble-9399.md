---
node_id: d42ae5a2-0cd3-53e1-8190-236a3721eea0
slug: brave-bramble-9399
title: Viz machinery
created_at: '2026-08-14T13:27:08+00:00'
parents:
- polished-pond-2718
summary: Bundler, single-file page, ported distance-field blobs with committed tuning, 500 nodes in 0.43s, and the two outputs that deliberately break the single-file property behind explicit flags.
flywheel:
  node_id: a186e182-d42d-5566-baad-44fe154b69df
  slug: soft-wave-9679
  revision: 0
  pushed_at: '2026-08-14T13:37:08+00:00'
  content_sha256: 0b821d246995737b86148ae0ecf3cfa93b6c09a757bb7c2b33fd909eb0d13dec
  parents_sha256: 8a5cac8569ae19b59da07c94ee132cf2455491411282f4f5f89fb128ce53eabb
  parents:
  - f4d676d8-a180-55fc-ae3f-54c1e4d3bcab
---
Status: working

## Current

How the page is built and what it costs — as distinct from what it shows [rec: gilded-pebble-5687].

- **Sources under `tools/viz/`** (an index.html skeleton, viz.css, fourteen JS parts and a manifest fixing their order) are concatenated into the `VIZ_TEMPLATE` constant by `tools/bundle_viz.py`; `viz --dev` reads them straight off disk for the edit loop, and `assemble_viz_template()` lives in hypergraph.py so the dev path and the constant cannot drift. Both hard properties are enforced by tests rather than by care: hypergraph.py stays one copyable file, and the default page stays self-contained [rec: southern-ivy-0706] [rec: tiny-stone-3934].
- **Blob geometry is excaligraph's signed distance field**, ported into `js/blob.js` (887 lines of TS → 562 of JS, MIT attribution kept, URL deliberately omitted so the page fetches nothing): per-shape signed distances, an MST corridor with obstacle-aware routing, smooth-min union and smooth-max subtraction of every non-member, marching squares with the ambiguous-cell rule, Douglas-Peucker simplification. The convex hull survives only as the fast fallback below a zoom threshold; a drag stays on the distance field and buys its frame rate with a coarser sampling pitch, a relaxed point budget, one recompute per animation frame, and labels anchored on last-known geometry until pointerup [rec: smooth-wolf-8655] [rec: tiny-stone-3934].
- **The tuning travels with the repo.** Eleven sliders in a collapsed sidebar panel, each showing its live value and marking itself when moved off the baseline, copyable as YAML; an optional `viz: blob:` block in `.hypergraph/config.yml` presets them through the existing `load_config`, so no new dependency and no Python version bump. Precedence is defaults → config → localStorage → live slider, and Reset returns to the config rather than to the hard default [rec: tiny-stone-3934].
- **The ~500-node scale target is met**: a synthetic 500-record/60-state fixture paints in 0.43s, down from 8.22s, with the small-graph baseline unchanged — a Barnes-Hut quadtree above 120 nodes with the exact loop kept below as both the cheaper path and the reference, a grid hash replacing the 40-pass card de-overlap, level of detail by zoom, a time window over the record graph, and hyperedge collapse to a single puck [rec: steady-haven-0365]. The browser scale guard measures first paint in the Everything view, at 560 nodes drawn [rec: tiny-stone-3934].
- **Two outputs deliberately break the single-file property, and each is an explicit flag.** `viz --format excaligraph` emits a YAML spec that `excaligraph build` turns into a hand-editable Excalidraw scene — verified end to end against this repo's graph with excaligraph's real CLI at 51 nodes / 57 edges / 12 hyperedges, every node keeping a `link:` back to its markdown source, and the status palette restated in Python as `PALETTE` with a test asserting every value still appears in the bundled page [rec: hollow-path-2087]. `viz --live` writes a sibling `viz.data.json`, polls it, and pulses every node that appeared since the last poll; on a change every derived cache is dropped, because a cache that survives a data swap is a drawing that looks live and is not, and `js/live.js` executes no network code unless the flag set `DATA.live` [rec: cold-rose-6963].
- Coverage went 117 → 151 tests over the seven phases, including a Playwright harness (dev group only, self-skipping) that measures every view in chromium against the frozen fixture [rec: wise-river-3571].

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
