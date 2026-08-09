---
node_id: 9a1d69c7-da13-5b1f-8c16-685e738ab22d
slug: hollow-path-2087
title: 'Viz phase 4: excaligraph spec export for hand-editable excalidraw figures'
created_at: '2026-08-09T10:01:53+00:00'
parents:
- vast-sage-0617
summary: viz --format excaligraph emits a spec excaligraph build turns into a valid Excalidraw scene; cross-graph edges default off because the first, complete figure was unreadable.
---
## What

Added `viz --format excaligraph`: a YAML graph spec that `excaligraph build`
turns into a hand-editable Excalidraw scene. Two-step by design — nothing in
`tools/hypergraph.py` shells out, and node stays optional and off the core path.

## Why

Follows `vast-sage-0617`. The interactive page is for reading; a paper figure has
to be editable by a human afterwards, which means it has to arrive as excalidraw
elements rather than as a screenshot. `~/excaligraph`'s `src/cli/spec.ts` already
defines the schema for exactly that, and Phase 2 already borrowed its blob
mathematics — so the export and the page draw the same picture by construction.

## Method

`excaligraph_spec()` maps: record + state nodes to `nodes` (each with a `link:`
back to `.hypergraph/graph/<kind>/<slug>.md`, so a reader in excalidraw can click
through to the source); parent edges to `edges`; each state node's impact set to
a `hyperedges` blob; `layout: {engine: dagre, rankdir: LR}`.

**The palette is restated in Python as `PALETTE`** and `test_palette_matches_the_page`
asserts every value still appears in the bundled page. Two copies of a colour
table is not ideal, but a *silently divergent* pair is much worse: the whole
point is that a figure and the page agree on what "broken" looks like.

Determinism: `seed` is derived from the project name, so a figure regenerated
next month has the same hand-drawn jitter as the one already in the paper.

## Result

Verified end to end against this repo's own graph, with excaligraph's real CLI:

```
excaligraph build hg.yaml -o hg.excalidraw   → 51 nodes, 57 edges, 12 hyperedges
excaligraph preview hg.excalidraw -o hg.svg  → 846 KB SVG
```

The scene is valid Excalidraw — `type: excalidraw`, `version: 2`, 195 elements
(50 rectangles, 1 ellipse for the state root, 57 arrows, 24 lines for the blob
outlines, 63 text) — and **all 51 nodes keep their `link:`** through the build.

**The first version built fine and was useless, which the acceptance criterion
would not have caught.** "Build and preview succeed" was true of a figure with
234 edges and paragraph-length labels on them: rendered, it is a solid mat of
orange text with the graph somewhere underneath. Two fixes:

1. **Cross-graph edges are off by default**, behind `--links
   none|provenance|impact|all`. This is Phase 3's focus/all idea applied to a
   static figure for the same reason, plus one that is specific to the export:
   the impact relation *is* the blob membership, so drawing it again as edges
   says nothing new. The default figure is 57 edges instead of 234.
2. **Edge labels are cut to 60 characters.** An impact delta is a paragraph —
   ~1000 characters in this graph. The full text is one click away via the node's
   `link:`.

Tests: 140 pass (was 135; +5 — spec shape, link targets, the `--links` counts,
label truncation, palette agreement, and the CLI path). Checker: 0 violations.
README documents the two-step.

One correction to the plan's acceptance criterion, worth stating because it reads
as satisfiable and is not: "the SVG opens in excalidraw.com unchanged". An SVG
does not open in excalidraw — the `.excalidraw` scene does, and the SVG is the
headless *render* of it. What was actually verified is that the scene is
structurally valid Excalidraw and that `preview` renders it.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: hg-viz
- commit: 9a4e8f23b3b2f319c7f638ea863f515a32cae9fa

## State Impact

- target: polished-pond-2718 — `viz --format excaligraph` emits a YAML graph spec that `excaligraph build` turns into a hand-editable Excalidraw scene, verified end to end against this repo's graph with excaligraph's real CLI: build gives 51 nodes / 57 edges / 12 hyperedges, preview renders an 846KB SVG, and the scene is structurally valid Excalidraw (type excalidraw, version 2, 195 elements) with all 51 nodes keeping the `link:` back to their markdown source. Mapping: record + state nodes -> nodes with links, parent edges -> edges, each state node's impact set -> a hyperedge blob, layout dagre LR, seed derived from the project name so a regenerated figure keeps the same jitter. The status palette is restated in Python as PALETTE and a test asserts every value still appears in the bundled page, so figures and the page cannot silently disagree on what 'broken' looks like. Two-step by design: nothing in hypergraph.py shells out and node stays optional. The first version built and previewed successfully and was still useless — 234 edges carrying paragraph-length impact deltas render as a mat of text over the graph — which is worth recording because 'build and preview succeed' was the stated acceptance criterion and it passed. Fixed by defaulting cross-graph edges off behind --links none|provenance|impact|all (the impact relation IS the blob membership, so drawing it again as edges says nothing new; 57 edges instead of 234) and cutting edge labels to 60 characters. Also corrected: the criterion 'the SVG opens in excalidraw.com unchanged' is not satisfiable as written — an SVG does not open in excalidraw, the .excalidraw scene does. Tests 135 -> 140, checker 0 violations, README documents the two-step.
