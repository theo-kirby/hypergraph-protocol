---
node_id: f4d676d8-a180-55fc-ae3f-54c1e4d3bcab
slug: polished-pond-2718
title: Visualization
created_at: '2026-08-06T22:17:38.572359+00:00'
parents:
- cool-king-8586
summary: 'The visualization seam, closed at both ends: the JSON exports are the pinned contract and hypergraph-viz is its live consumer, attached through a stdlib adapter with one-command attach/detach; remaining opens are viewer-side.'
flywheel:
  node_id: f4d676d8-a180-55fc-ae3f-54c1e4d3bcab
  slug: polished-pond-2718
  revision: 12
  pushed_at: '2026-08-30T11:32:39+00:00'
  content_sha256: ec4091fed910ad9b42e652f4f90f3eefd7787d01ea80ce95a813157bfea00d38
  parents_sha256: a7a7d736bcfc7a886dc3bd4b6b138fcbabbc3a0bb49408b1c19e0413f4420ad9
  parents:
  - 9e687be1-1c80-56a2-bc0c-d4476edc0a2e
---
Status: working

## Current

The in-core visualizer is removed at 0.0.9. The viz section, the ~3,700-line embedded page template, the page sources, the bundler, the viz test suite, the browser baselines and the viz-only fixtures all left the repo, and `hypergraph viz` survived as a signpost stub until the 0.1.0 gate removed it: the CLI now carries no viz entry at all [rec: loyal-tide-3608] [rec: steady-ember-8009].

- **What remains in core is the contract, and it was already there.** `export` writes `.hypergraph/cache/{record,state}.json`, and any renderer that reads those files can draw both graphs — backend/local-adapter.md had already named the exports as the whole integration surface [rec: loyal-tide-3608] [rec: steady-ember-8009].
- **The contract is pinned empirically, not just named** [rec: bold-sand-5009]. A committed stdlib-only probe plus JSON baseline (`.hypergraph/evidence/2026-08-16-export-contract-*`) measures what a consumer may rely on: nine node keys always present with stable types, UUID ids and `words-####` slugs unique throughout, parents resolving in-file, both graphs acyclic and disjoint with exactly one root each, SPEC-I6 statuses on every non-root state node. Zero findings.
- **The consumer exists and is connected** [rec: round-arrow-5061]. `hypergraph-viz` (separate repo, excaligraph-based: record/state modes, fold/unfold, hyperedge blobs over the record graph, tune panel, SVG export) reads the exports through `make-viz-data.py`, a stdlib-only adapter that lives in the consumer's repo — core gained no viz code. Each non-root state node's inline record citations become its hyperedge over the record graph. Verified against this project: 113 record/25 state nodes, 24 of 24 aspects resolved with 0 dangling members; the dev server and the production build both render the real graphs.
- **Attach/detach is one command each** [rec: round-arrow-5061]: `python3 make-viz-data.py <project-root>` writes the viewer's `data.local.js` (gitignored, per-machine); `--detach` removes it and the built-in demo returns. Any project with the exports attaches the same way.
- **The capability lost with the old page was named and accepted, not overlooked.** The interactive page (five views, force layout, live mode) is gone from this repo, not moved; git history at fbf18f2 keeps it recoverable if hypergraph-viz wants to absorb it [rec: loyal-tide-3608].
- Both children — **Viz machinery** and **Views** — are superseded by this node's seam claim; their bodies keep the record of what the page was and what building it taught [rec: loyal-tide-3608].
- **Open, viewer-side only**: the viewer does not yet render node status (frontier nodes are not visually distinct from working ones), and cross-repo provenance stays prose [rec: round-arrow-5061]. Neither is a contract change.

## Negative knowledge

None here — the lessons from building the page live on the two superseded children.

## Provenance

- long-tree-4179 — the viz subcommand added, sharing the checker's parsers
- morning-rain-7488 — the force-directed hyperedge-blob view the unified view built on
- gilded-pebble-5687 — the decision behind the seven-phase overhaul and its measured motivation
- southern-ridge-1802 — Operator directive requesting viz improvements
- late-sage-5549 — split into machinery and views
- loyal-tide-3608 — the viz cut: visualization leaves core, the JSON exports become the contract
- bold-sand-5009 — the second dispatch's unit: the export contract probed and baselined at zero findings
- steady-ember-8009 — the stub's removal at the 0.1.0 gate: no viz entry in the CLI at all
- round-arrow-5061 — the consumer lands: hypergraph-viz attached through the make-viz-data.py adapter, one-command attach/detach
