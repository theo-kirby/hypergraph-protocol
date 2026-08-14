---
node_id: f4d676d8-a180-55fc-ae3f-54c1e4d3bcab
slug: polished-pond-2718
title: Visualization
created_at: '2026-08-06T22:17:38.572359+00:00'
parents:
- cool-king-8586
summary: A self-contained interactive page over both graphs, sharing the checker's parsers; splits into what it shows (Views) and how it is built and what it costs (Viz machinery).
flywheel:
  node_id: f4d676d8-a180-55fc-ae3f-54c1e4d3bcab
  slug: polished-pond-2718
  revision: 8
  pushed_at: '2026-08-14T13:37:04+00:00'
  content_sha256: d83a108194db206a4c472b5db0d9404a5a6ef42fd6d1a7a8b1806382719c4b4a
  parents_sha256: a7a7d736bcfc7a886dc3bd4b6b138fcbabbc3a0bb49408b1c19e0413f4420ad9
  parents:
  - 9e687be1-1c80-56a2-bc0c-d4476edc0a2e
---
Status: working

## Current

`tools/hypergraph.py viz` emits a self-contained interactive HTML page over both graphs. It splits into two things that fail differently and are therefore separate children of this node: **Views**, which is what the page shows and whether a reader can read it, and **Viz machinery**, which is how the page is built and what it costs to draw [rec: gilded-pebble-5687] [rec: late-sage-5549].

- **It shares the checker's parsers.** The viz subcommand reuses the section, impact and citation parsers and the export normalization, so the picture and the invariants cannot disagree about what a node says [rec: long-tree-4179].
- **The whole overhaul was driven by a measured defect and closed against the same measurements**, rather than by taste: fit zoom, edges drawn, and labels rendered, all on a frozen snapshot of this repo's own graph [rec: gilded-pebble-5687].
- **The page is the only artifact that shows both graphs at once**, which is what makes it the cross-graph structure's exhibit rather than a convenience [rec: southern-ridge-1802].

## Negative knowledge

None here — the machinery and view lessons live on the two children.

## Provenance

- long-tree-4179 — the viz subcommand added, sharing the checker's parsers
- morning-rain-7488 — the force-directed hyperedge-blob view the unified view built on
- gilded-pebble-5687 — the decision behind the seven-phase overhaul and its measured motivation
- southern-ridge-1802 — Operator directive requesting viz improvements
- late-sage-5549 — split into machinery and views
