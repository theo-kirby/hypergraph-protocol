---
node_id: f4d676d8-a180-55fc-ae3f-54c1e4d3bcab
slug: polished-pond-2718
title: Visualization
created_at: '2026-08-06T22:17:38.572359+00:00'
parents:
- cool-king-8586
summary: 'The visualization seam after the 0.0.9 cut: JSON exports are the contract, hypergraph-viz (on excaligraph) is the planned consumer, viz is a signpost stub; open until the consumer exists.'
flywheel:
  node_id: f4d676d8-a180-55fc-ae3f-54c1e4d3bcab
  slug: polished-pond-2718
  revision: 9
  pushed_at: '2026-08-16T16:38:33+00:00'
  content_sha256: ca060f6e3ac08b3eba39cdf0d1568f98c3aba4dbcfada519449e54fcd9125da5
  parents_sha256: a7a7d736bcfc7a886dc3bd4b6b138fcbabbc3a0bb49408b1c19e0413f4420ad9
  parents:
  - 9e687be1-1c80-56a2-bc0c-d4476edc0a2e
---
Status: open

## Current

The in-core visualizer is removed at 0.0.9. The viz section, the ~3,700-line embedded page template, the page sources, the bundler, the viz test suite, the browser baselines and the viz-only fixtures all left the repo, and `hypergraph viz` is now a signpost stub: it prints where visualization went and exits 2 [rec: loyal-tide-3608].

- **What remains in core is the contract, and it was already there.** `export` writes `.hypergraph/cache/{record,state}.json`, and any renderer that reads those files can draw both graphs — backend/local-adapter.md had already named the exports as the whole integration surface, which is why this cut was the first of the planned restructuring: nothing downstream changes. The `viz:` block in `.hypergraph/config.yml` stays legal as display configuration for external tooling; core never reads it and no invariant does either [rec: loyal-tide-3608].
- **The planned consumer is hypergraph-viz**, a thin npm-ecosystem translator built on excaligraph — a standalone general library with native hyperedge blobs and a conformance harness against Excalidraw's own `restore()`. This node is `open` because the capability is currently a contract whose consumer does not exist yet [rec: loyal-tide-3608].
- **The capability lost was named and accepted, not overlooked.** The interactive page (five views, force layout, live mode) is gone from this repo, not moved; Excalidraw scenes are static but hand-editable. Git history at fbf18f2 keeps the page recoverable if hypergraph-viz wants to absorb it [rec: loyal-tide-3608].
- Both children — **Viz machinery** and **Views** — are superseded by this node's seam claim; their bodies keep the record of what the page was and what building it taught [rec: loyal-tide-3608].

## Negative knowledge

None here — the lessons from building the page live on the two superseded children.

## Provenance

- long-tree-4179 — the viz subcommand added, sharing the checker's parsers
- morning-rain-7488 — the force-directed hyperedge-blob view the unified view built on
- gilded-pebble-5687 — the decision behind the seven-phase overhaul and its measured motivation
- southern-ridge-1802 — Operator directive requesting viz improvements
- late-sage-5549 — split into machinery and views
- loyal-tide-3608 — the viz cut: visualization leaves core, the JSON exports become the contract
