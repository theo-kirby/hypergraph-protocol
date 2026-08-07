---
node_id: 5fa9c7fd-59c2-5755-8956-803c4ce9ff1d
slug: long-tree-4179
title: 'Visualization: interactive record/state/hypergraph viz subcommand shipped'
created_at: '2026-08-06T22:16:57.085813+00:00'
parents:
- steep-cell-5173
- flat-pine-9555
summary: Interactive self-contained HTML viz (record/state/hypergraph views) added as tools/hypergraph.py viz; 20 tests green.
flywheel:
  node_id: 5fa9c7fd-59c2-5755-8956-803c4ce9ff1d
  slug: long-tree-4179
  revision: 1
  pushed_at: '2026-08-07T18:12:00.956635+00:00'
  content_sha256: 1ddc62e58d59df7cea88f38bb91b09593a5eb764423fbc29e05bc0ea5be1e8d4
---
## What

Added a `viz` subcommand to tools/hypergraph.py that emits a self-contained interactive HTML visualization of a Hypergraph project: a Record view (causal DAG), a State view (architecture tree, status-colored, frontier emphasized), and a combined Hypergraph view rendering the two graphs side by side with cross-graph links. Plus a 9-case pytest suite, README/SPEC documentation, and a live demo generated from this repo's own exports.

## Why

"State graph visualizer" was on SPEC.md's future-work list; with the v0.0.1 dogfood cycle complete (steep-cell-5173) the cache exports and their edge-encoding normalization (flat-pine-9555) were in place to build on. The hypergraph's defining structure — many-to-one markdown provenance across two disjoint DAGs — is exactly what a text rendering shows worst and a two-column linked visualization shows best.

## Method

Compared stacks before building: Python static (graphviz/matplotlib/mermaid — system binary or heavy deps, node bodies unreachable, many-to-one provenance renders as clutter) vs JS graph libraries (Cytoscape+dagre/D3/vis-network/Sigma — 0.3–1MB vendored or CDN-fetched, generic force layouts fight the layered-DAG + bipartite-provenance shape) vs zero-dependency generated HTML. Chose the last: deterministic layout computed in Python (longest-path layering + 4-sweep barycenter ordering per graph; topological/DFS two-column ordering for the hypergraph view), vanilla JS+SVG interaction layer (pan/zoom, node drag, click-for-detail side panel with rendered node content and clickable slugs, search filter, deep links #record/#state/#<slug>). Cross-links parsed with the checker's own parsers: state→record from ## Provenance lines + inline [rec:] cites + negative-knowledge evidence slugs; record→state from ## State Impact targets, with NEW targets resolved by kebab(title) match. HWM and unreconciled record nodes flagged from the state root's ## Reconciliation. All SVG styling is attribute-level so the SVG download button emits standalone files; print CSS covers PDF export. Status palette taken from a colorblind-validated reference set, with separately-stepped light and dark themes; status is always shown as text beside color. Verified end-to-end via headless-chromium screenshots: all three views, node selection + dimming, dark mode.

## Result

`uv run tools/hypergraph.py viz --record … --state … --config … -o .hypergraph/viz.html` produces a 55KB single file, zero network requests, opens from file://. Test suite: 20 passed (11 existing checker + 9 new viz cases covering payload shape, provenance/impact link extraction incl. NEW resolution, root exclusion, HWM/unreconciled flags, layout determinism, HTML self-containment, CLI exit codes). No new Python deps (pyyaml only), no JS deps. .hypergraph/viz.html gitignored alongside cache/.

## Repo

- repo: https://github.com/theo-kirby/hypergraph
- branch: main
- commit: b0e0e8bd2899cbf65b7462e9144be9869d403446 (HEAD at recording time; viz work sits in the working tree, commit pending)

## State Impact

- target: NEW visualization — component created, status working: `viz` subcommand renders interactive record/state/hypergraph views from cache exports, tested and screenshot-verified
- target: wandering-sun-8831 — new claim: tools/hypergraph.py gains a third subcommand (`viz`) reusing the checker's parsers; suite now 20 tests green