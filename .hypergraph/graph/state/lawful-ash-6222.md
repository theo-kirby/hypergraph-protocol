---
node_id: 7f305497-435c-583e-b858-bd1fd521e073
slug: lawful-ash-6222
title: Views
created_at: '2026-08-14T13:27:26+00:00'
parents:
- polished-pond-2718
summary: Five job-named views with Everything as the boot default; the rename measured at both ends by fit zoom; tag chips that change no geometry; open on rendering any graph but this project's own.
flywheel:
  node_id: 8bcba412-85bd-5a89-a05a-a31d843acee9
  slug: yellow-hill-6987
  revision: 0
  pushed_at: '2026-08-14T13:37:08+00:00'
  content_sha256: b254f6feabd5212d930e7f30c6a52e860aadb9d3ff44507009834cb7c75c2409
  parents_sha256: 8a5cac8569ae19b59da07c94ee132cf2455491411282f4f5f89fb128ce53eabb
  parents:
  - f4d676d8-a180-55fc-ae3f-54c1e4d3bcab
---
Status: working

## Current

Five views named after the job each does, with **Everything** as the boot default — both graphs, circles, force layout, all link kinds and all four edge toggles on. The four focused views are each a deliberate slice, one click or one number key away; opening on the narrowest of them asked a first-time reader to pick a slice of something they had not seen [rec: tiny-stone-3934].

- **Timeline** — the record graph as `git log --graph` lanes, x by rank or by real dates with clamped gaps, a lane ruler and date gutter, the high-water mark drawn as a rule with the unreconciled tail tinted [rec: rough-moss-4912].
- **Frontier** — the state graph as a status board (broken | blocked | open | working | superseded), frontier columns first, empty columns kept as labelled rails, with an architecture-tree toggle mirroring STATE.md [rec: rough-moss-4912].
- **Provenance** — both graphs in columns, with the state column ordered by the mean `chrono` of the record work each claim cites. Cross-graph links carry a mode — focus (default) | all | none — orthogonal to the per-kind checkboxes: the checkboxes say which kinds may draw, the mode says how many. Focus draws only the selected or hovered node's links, so it opens with zero of 177; `all` routes each claim's links through a staggered vertical spine as bundled ribbons without arrowheads [rec: vast-sage-0617].
- **Clusters** — each claim's record set as a distance-field blob, laid out by a two-level force sim that settles the hyperedges as bodies first and then the nodes toward their cluster centre [rec: smooth-wolf-8655].
- **The rename was measured at both ends.** Fit zoom went 0.183 → 1.0 (Timeline), 0.283 → 1.0 (Frontier), 0.208 with 234 edges drawn → 1.057 with zero cross-links until asked (Provenance), and 0.877 with 12 unlabelled convex hulls → 0.918 with 12 blobs and 39 labels (Clusters), on a frozen 39-record/12-state snapshot of this repo's own graph [rec: gilded-pebble-5687] [rec: southern-ivy-0706] [rec: wise-river-3571]. This supersedes the earlier toggle-driven single view with Record/State/Columns/Force presets [rec: long-tree-4179] [rec: still-forest-9161]; the pre-rename hashes still deep-link, and `#<slug>` still jumps to a node [rec: southern-ivy-0706].
- **A tag chip row filters and changes no geometry and no colour** — one chip per tag, OR within the selection, ANDed with the search box, hidden entirely on a graph with no tags. A tag has no standing in the protocol, so letting one restyle a node would give it standing in the picture that it has nowhere else; a browser test renders the same graph with and without tags and compares every shape [rec: clear-moss-4527].
- **The record-node panel has an Evidence section** listing that node's `artifacts:` paths as plain `<code>`, never as links: the page is emailed and committed, so a `file://` that resolves on one machine and 404s on every other reads worse than the path itself. No existence flag is baked in either — a "missing" computed at render time is a stale claim about somebody else's filesystem. The **state**-node payload has no `artifacts` key at all, and that absence is the documentation for "evidence lives on record nodes" [rec: shady-bay-7654].
- **Open: every view so far has been measured on this project's own graph.** The nine-run benchmark dataset is the first real external subject and it is renderable, but it came from a harness later found to be uncontrolled, so it is a rendering subject and not a source of claims [rec: ancient-dew-4488] [rec: staid-field-2723] [rec: southern-ridge-1802].

## Negative knowledge

- [scope: fit-to-window in a graph viewer | confidence: high | evidence: rough-moss-4912] a zoom floor does not make a view readable, it only stops it disappearing: at the 0.45 floor an 11.5px label renders at 5px. Fitting has to be axis-aware — a timeline fits height and scrolls through time, a board or column view fits width and scrolls down, both capped at 1:1 — and a view that still does not fit must scroll rather than shrink.
- [scope: reducing crossings in a dense bipartite provenance view | confidence: high | evidence: vast-sage-0617] barycentre ordering has a low ceiling when the links are genuinely dense: 4146 inverted pairs in architecture order → 3599 in barycentre order, −13.2%, with median ordering worse (3673). Ordering is not the lever when 86 of 89 provenance links are *declared* rather than incidental; drawing fewer links is.
- [scope: drawing reconciliation history from a graph export | confidence: high | evidence: rough-moss-4912] past high-water marks are not recoverable — the export carries only the current one and previous values are recorded nowhere — so a timeline can mark where the frontier is now, not where it has been.
- [scope: accepting a generated figure | confidence: high | evidence: hollow-path-2087] "the build and the preview both succeed" is not a legibility test and passed on a figure that was useless: 234 edges carrying paragraph-length impact deltas render as a mat of text over the graph. An acceptance criterion for a figure has to name what must be readable in it.

## Provenance

- long-tree-4179 — the original three-view viz
- still-forest-9161 — tabs collapsed into the toggle-driven unified view this supersedes
- gilded-pebble-5687 — the seven-phase overhaul, its measured motivation, and the source split
- southern-ivy-0706 — views renamed; browser baselines captured; deep links preserved
- rough-moss-4912 — git-log lanes, the status board, axis-aware fitting
- smooth-wolf-8655 — the Clusters view's distance-field blobs and two-level layout
- vast-sage-0617 — link modes, the bundled spine, the barycentre-ordered state column
- wise-river-3571 — legend, keyboard, dark theme, export across all four views
- tiny-stone-3934 — Everything as the boot default, and why the narrowest view was the wrong one
- clear-moss-4527 — tag chips: a filter that changes nothing about how a node is drawn
- shady-bay-7654 — the Evidence section, and the state payload's deliberate silence
- ancient-dew-4488 — the nine-run dataset lands as the first external subject
- staid-field-2723 — that dataset qualified: renderable, but not a source of claims
- southern-ridge-1802 — every view so far measured on this project's own graph
