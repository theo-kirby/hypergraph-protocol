---
node_id: c22ed62a-8c21-588a-ac0a-7bf52affeb49
slug: wise-river-3571
title: 'Viz phase 7: legend, keyboard, dark-theme and export pass — the overhaul lands'
created_at: '2026-08-09T10:24:20+00:00'
parents:
- steady-haven-0365
summary: Legend rewritten for the four views and their new marks, keyboard shortcuts, dark theme verified, SVG export fixed to cover all four layouts at full detail.
flywheel:
  node_id: f6b6de60-6126-5155-b7c0-3213b995beb2
  slug: royal-shadow-4576
  revision: 2
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: 199e69a4033106dc4846b3ad29a40742d9b1c1e2275f0a01ed3ca6586336c9dc
  parents_sha256: eb1dab82e748a29b4ba61634161f2b3ef6d68e1a2cc9ccd97c311b866afa22b6
  parents:
  - bef7fb84-f75a-5f17-b30f-4ae956753183
---
## What

Landed the overhaul: rewrote the legend around the four views and the marks that
arrived with them, added keyboard shortcuts, checked every view in dark theme,
and made the SVG export cover all four layouts instead of the two it predated.

## Why

Follows `steady-haven-0365`. Six phases of new marks — lanes, a date gutter, the
unreconciled band, board rails, pucks, bundled ribbons, the time window — were
explained nowhere. A legend that describes the previous design is worse than no
legend, because it is confidently wrong.

## Method

**Legend**: a Views table saying what each of the four answers, and a "marks worth
knowing" table for the ones a reader cannot guess (lane rules, pucks, Window).
The old table of edge species stays — it was still true.

**Keys**: `1`–`4` pick a view, `/` focuses the search box, `f` fits, `Esc` clears
the selection and blurs the search. Nothing fires while typing and nothing takes a
modifier, so no browser shortcut is shadowed.

**Export**: `worldBounds` already learned about each layout's scenery in Phase 1,
so the SVG export now calls it rather than carrying its own hand-written
adjustment for the one arrangement that existed when it was written. Two real
defects fell out of testing it across all four views: the export inherited the
current zoom's level-of-detail, so an SVG taken while zoomed out silently shipped
`display:none` on its labels; and the `#furniture` and `#crosslinks` layers were
never checked. It now forces full detail for the file and restores the screen's
afterwards.

**Dark theme** was checked view by view. Everything new was already reading from
the theme table rather than hardcoding a colour, so nothing needed changing —
worth recording as a *verified* result rather than an assumed one.

## Result

Tests: 151 pass (was 148; +3 — SVG export across all four views including the
standalone and full-detail properties, and the keyboard map including the case
where typing "1" into the search box must not switch views). Checker: 0
violations.

End to end on this repo's live graph (46 record nodes now, 184 cross-links):
Timeline 8082x197 at zoom 1.0, Frontier 716x946 at 1.0, Provenance 1028x4246 at
1.057 with zero cross-links drawn, Clusters 1038x815 at 0.918 with 12 blobs. No
console errors in any view.

**The page now shows its own construction**: the seven viz record nodes sit in
the bottom-right of Clusters as their own amber cluster — amber because they are
past the high-water mark, which is exactly what the mark is for.

The whole overhaul, measured on the frozen fixture, first to last:

| view | before | after |
| --- | --- | --- |
| Timeline | 0.183 zoom, 847x4121 | 1.0, 6864x197 |
| Frontier | 0.283, 3295x201 | 1.0, 716x946 |
| Provenance | 0.208, 234 edges drawn | 1.057, **0** cross-links until asked |
| Clusters | 0.877, 12 hulls, 0 labels | 0.918, 12 field blobs, 39 labels |
| 500 nodes | (never tried) | 0.43s first paint |

Tests 117 -> 151 over the seven phases. The page is still one self-contained file
built from `tools/viz/`, and `tools/hypergraph.py` is still one file you can copy
anywhere and run.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: hg-viz
- commit: b97aa06ca39ac9e17758f1941b1f9b622d67682a

## State Impact

- target: polished-pond-2718 — the viz overhaul is complete and the claim can be stated without qualification now. Final phase: the legend was rewritten around the four views and the marks introduced along the way (lane rules, the unreconciled band, board rails, pucks, bundled ribbons, the time window) — a legend describing the previous design is worse than none, because it is confidently wrong; keyboard shortcuts landed (1-4 views, / search, f fit, Esc clear) with typing and modifiers deliberately excluded so no browser shortcut is shadowed; the SVG export now uses worldBounds so all four layouts export whole, and two defects surfaced from testing it across every view — the export inherited the current zoom's level of detail, silently shipping display:none on labels in a file taken while zoomed out, and the furniture and crosslinks layers had never been checked. Dark theme was verified view by view and needed no changes, everything new already reading the theme table. Whole-overhaul result on the frozen fixture: Timeline 0.183 zoom -> 1.0, Frontier 0.283 -> 1.0, Provenance 0.208 with 234 edges drawn -> 1.057 with zero cross-links until asked, Clusters 0.877 with 12 convex hulls and no labels -> 0.918 with 12 distance-field blobs and 39 labels, plus a 500-node graph painting in 0.43s where the shape had never been tried. Tests 117 -> 151 across the seven phases, checker 0 violations. Both hard properties held throughout: hypergraph.py is still one copyable file and the default page is still self-contained, now enforced by tests rather than by care. End to end on the live graph (46 record nodes, 184 cross-links) every view renders without console errors, and the page shows its own construction — the seven viz record nodes form their own amber cluster past the high-water mark.
