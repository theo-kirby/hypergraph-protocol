---
node_id: f4d676d8-a180-55fc-ae3f-54c1e4d3bcab
slug: polished-pond-2718
title: Visualization
created_at: '2026-08-06T22:17:38.572359+00:00'
parents:
- cool-king-8586
summary: Unified toggle-driven interactive viz (presets Record/State/Columns/Force) supersedes the four tabs; deterministic, self-contained, smoke-tested.
flywheel:
  node_id: f4d676d8-a180-55fc-ae3f-54c1e4d3bcab
  slug: polished-pond-2718
  revision: 2
  pushed_at: '2026-08-07T18:12:06.426139+00:00'
  content_sha256: a22c1dd604fdf9f740074c81670873773792530ace33a8b0c0809c0f8cba220f
---
Status: working

## Current

- tools/hypergraph.py `viz` emits a self-contained interactive HTML visualization: a single unified view driven by display toggles — graph visibility (record / state / both), node style (cards / circles), layout (layered / force, independent of style), and per-species edge toggles (parent edges, impact links, provenance links, hyperedge blobs) — with preset chips Record, State, Columns, and Force reproducing the classic arrangements [rec: long-tree-4179] [rec: morning-rain-7488] [rec: still-forest-9161].
- The prior four-tab layout (Record/State/Combination/Hypergraph) is superseded by the toggle-driven view: Operator use found the tabs were four fixed points in a toggle space and "Combination" mislabeled the model (every arrangement is a hypergraph presentation); deep links #record/#state/#combo/#combination/#hyper map onto presets, #<slug> jumps to a node [rec: still-forest-9161].
- Zero JS dependencies and zero network requests; deterministic layouts throughout — Python-side longest-path layering + barycenter for layered mode, hash-seeded force simulation (no Math.random) generalized to any visible graph set with structure-derived springs and a bounded card de-overlap pass for force mode [rec: long-tree-4179] [rec: morning-rain-7488] [rec: still-forest-9161].
- Chrome: slim icon header (fit, theme, SVG/PDF export menu), sidebar holding search + Display toggles, resizable and collapsible via a draggable divider; position/pan caches key on layout signature so edge-toggle flips never reset pan/zoom or node drags [rec: still-forest-9161].
- Verified end-to-end in headless browsers: chromium screenshots for the original views, and a 24-check Playwright smoke pass covering preset fidelity, custom toggle mixes, deep links, divider interactions, and SVG export; 11 viz pytest cases over shared fixtures, full suite 22 green [rec: long-tree-4179] [rec: morning-rain-7488] [rec: still-forest-9161].
- The benchmark dataset now exists and is the first real external subject for this work: 9 runs x (fidelity by section, cold-start timings, per-turn token/tool traces) in `research/runs/main/analysis.json`, with the raw session transcripts harvested alongside [rec: ancient-dew-4488]. It is first-run data from a harness later found to be uncontrolled (protocol-benchmark-4417), so it is a rendering subject, not a source of claims [rec: staid-field-2723].
- Improvements requested by the Operator (2026-08-08); scope not yet set. The protocol benchmark's run data — nine runs across four measures (protocol-benchmark-4417) — is the intended first real dataset to render, which would make it the first viz work with an external subject rather than the project's own graph [rec: southern-ridge-1802].

## Negative knowledge

None yet.

## Provenance

- long-tree-4179 — stack comparison decision, original three-view viz, tests, screenshot verification
- morning-rain-7488 — force-directed hyperedge-blob view; hyperedges/hull/blob machinery the unified view builds on
- still-forest-9161 — tabs collapsed into the unified toggle-driven view with presets; chrome redesign
- southern-ridge-1802 — Operator directive requesting viz improvements; benchmark data named as the first dataset
- ancient-dew-4488 — the nine-run dataset lands as the first external subject
- staid-field-2723 — that dataset qualified: renderable, but not a source of claims
