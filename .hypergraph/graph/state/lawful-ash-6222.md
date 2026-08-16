---
node_id: 7f305497-435c-583e-b858-bd1fd521e073
slug: lawful-ash-6222
title: Views
created_at: '2026-08-14T13:27:26+00:00'
parents:
- polished-pond-2718
summary: 'Superseded at 0.0.9: the five views left with the page; body kept as the record of the job-named views and the legibility lessons that transfer to hypergraph-viz.'
flywheel:
  node_id: 8bcba412-85bd-5a89-a05a-a31d843acee9
  slug: yellow-hill-6987
  revision: 1
  pushed_at: '2026-08-16T16:38:33+00:00'
  content_sha256: 2a8c96e5c1ef85d72a421cdc0a6773b0ae342cf201a849b64c07920097d204d3
  parents_sha256: 8a5cac8569ae19b59da07c94ee132cf2455491411282f4f5f89fb128ce53eabb
  parents:
  - f4d676d8-a180-55fc-ae3f-54c1e4d3bcab
---
Status: superseded

## Current

**Superseded**: the page these views lived on was removed from the repo at 0.0.9 with the viz cut; the seam that replaces it is described by the parent node, **Visualization** (`polished-pond-2718`), and the job the views did passes to hypergraph-viz when it exists [rec: loyal-tide-3608]. What follows is the record of what the views were and what designing them taught.

- **Five views named after the job each did**, with **Everything** as the boot default — both graphs, circles, force layout, all link kinds on. Opening on the narrowest view asked a first-time reader to pick a slice of something they had not seen [rec: tiny-stone-3934].
- **Timeline** — the record graph as `git log --graph` lanes, the high-water mark drawn as a rule with the unreconciled tail tinted; **Frontier** — the state graph as a status board, frontier columns first, empty columns kept as labelled rails [rec: rough-moss-4912]. **Provenance** — both graphs in columns, cross-graph links defaulting to focus so it opened with zero of 177 drawn [rec: vast-sage-0617]. **Clusters** — each claim's record set as a distance-field blob [rec: smooth-wolf-8655].
- **The view rename was measured at both ends** — fit zoom improved on every view on a frozen snapshot of this repo's own graph [rec: gilded-pebble-5687] [rec: southern-ivy-0706] [rec: wise-river-3571]. It superseded the earlier toggle-driven single view [rec: long-tree-4179] [rec: still-forest-9161].
- **A tag chip row filtered and changed no geometry and no colour** — a tag has no standing in the protocol, so letting one restyle a node would give it standing in the picture that it has nowhere else [rec: clear-moss-4527].
- **The record-node panel had an Evidence section** listing `artifacts:` paths as plain `<code>`, never as links, with no baked-in existence flag — a "missing" computed at render time is a stale claim about somebody else's filesystem. The state-node payload had no `artifacts` key at all [rec: shady-bay-7654].

## Negative knowledge

- [scope: fit-to-window in a graph viewer | confidence: high | evidence: rough-moss-4912] a zoom floor does not make a view readable, it only stops it disappearing: at the 0.45 floor an 11.5px label renders at 5px. Fitting has to be axis-aware — a timeline fits height and scrolls through time, a board or column view fits width and scrolls down, both capped at 1:1 — and a view that still does not fit must scroll rather than shrink.
- [scope: reducing crossings in a dense bipartite provenance view | confidence: high | evidence: vast-sage-0617] barycentre ordering has a low ceiling when the links are genuinely dense: 4146 inverted pairs in architecture order → 3599 in barycentre order, −13.2%, with median ordering worse (3673). Ordering is not the lever when 86 of 89 provenance links are *declared* rather than incidental; drawing fewer links is.
- [scope: drawing reconciliation history from a graph export | confidence: high | evidence: rough-moss-4912] past high-water marks are not recoverable — the export carries only the current one and previous values are recorded nowhere — so a timeline can mark where the frontier is now, not where it has been.
- [scope: accepting a generated figure | confidence: high | evidence: hollow-path-2087] "the build and the preview both succeed" is not a legibility test and passed on a figure that was useless: 234 edges carrying paragraph-length impact deltas render as a mat of text over the graph. An acceptance criterion for a figure has to name what must be readable in it.

## Provenance

- long-tree-4179 — the original three-view viz
- still-forest-9161 — tabs collapsed into the toggle-driven unified view this superseded
- gilded-pebble-5687 — the seven-phase overhaul, its measured motivation, and the source split
- southern-ivy-0706 — views renamed; browser baselines captured; deep links preserved
- rough-moss-4912 — git-log lanes, the status board, axis-aware fitting
- smooth-wolf-8655 — the Clusters view's distance-field blobs and two-level layout
- vast-sage-0617 — link modes, the bundled spine, the barycentre-ordered state column
- wise-river-3571 — legend, keyboard, dark theme, export across all four views
- tiny-stone-3934 — Everything as the boot default, and why the narrowest view was the wrong one
- clear-moss-4527 — tag chips: a filter that changes nothing about how a node is drawn
- shady-bay-7654 — the Evidence section, and the state payload's deliberate silence
- hollow-path-2087 — the excaligraph-figure legibility lesson
- loyal-tide-3608 — the viz cut removed the page these views lived on
