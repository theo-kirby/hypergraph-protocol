---
node_id: 788e3f6f-4a4a-50ae-8e39-b177508f218f
slug: southern-ivy-0706
title: 'Viz phase 0: viz sources split behind a build-time bundler, views renamed, browser baselines captured'
created_at: '2026-08-09T09:25:50+00:00'
parents:
- gilded-pebble-5687
summary: Byte-identical split of the viz page into tools/viz/ with a bundler, a --dev source path, job-named views, and a Playwright baseline that quantifies the unreadable views.
flywheel:
  node_id: aaf73ebd-875b-5d53-9b6c-5ed43f828b02
  slug: crimson-poetry-6961
  revision: 0
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: 0cea949e0ca8d9e33f8fa0da132c31533aceff783e41aa9a313c44f0d1069941
  parents_sha256: afbfc5b16dcd85afbeb3aa680f99e63f452ea934f7649ea3f4e8a13549b86d08
  parents:
  - 0b4fc69b-7646-5435-bf1f-f967982c87fb
---
## What

Built the foundation for the viz overhaul: split the page out of the single-file
script into `tools/viz/`, added `tools/bundle_viz.py` to concatenate it back into
the `VIZ_TEMPLATE` constant, added a `viz --dev` path that reads the sources
directly, renamed the four views after the job each does, and stood up a
Playwright harness that measures every view in a real browser and screenshots it.
No layout changed — this phase exists so the later ones can be reviewed.

## Why

Follows `gilded-pebble-5687`, which set the direction. Three hard constraints
made "just split it into modules" impossible: `tools/hypergraph.py` carries a
PEP 723 header and must stay one copyable file, the emitted HTML must stay
self-contained, and `tests/test_packaging.py` enforces an allow-list distribution.
The resolution is to split the *sources* and bundle at build time, with a test
that fails if the two drift.

## Method

**Split.** `tools/viz/` now holds `index.html` (skeleton with `/*{{CSS}}*/`,
`/*{{JS}}*/`, `__TITLE__`, `__VIZ_DATA__`), `viz.css`, and nine JS parts:
`core, layout-force, layout-columns, blob, render, panel, controls, export, boot`.
`manifest.json` fixes the concatenation order so no bundler dependency is needed.
Parts join **verbatim** — no separator is inserted, so the blank line between two
sections belongs to the end of the preceding file. That choice is what makes the
move exactly reversible.

**Assembly lives in `hypergraph.py`**, not in the bundler: `assemble_viz_template()`
is what `viz --dev` calls, and `tools/bundle_viz.py` imports it. One
implementation, so the dev path and the bundled constant cannot disagree.
`bundle_viz.py --check` exits 1 when stale; it refuses to bundle a payload
containing `"""` or ending in a backslash, either of which would break the
`r"""` constant.

**View rename**, with the pre-rename deep links kept as aliases via `VIEW_ALIASES`:
`#record`→Timeline, `#state`→Frontier, `#combo`/`#combination`→Provenance,
`#hyper`→Clusters.

**Browser harness.** `playwright` went into `[dependency-groups] dev` only;
`tests/browser/` skips its own collection when playwright or chromium is missing,
so a bare checkout stays green. Tests measure through the DOM the page actually
produced — no test-only hooks in the page. `tools/fixtures/self/` freezes this
repo's graph (39 record, 12 state, 177 links) so baselines stay stable while the
live graph grows.

Phase-0 PNGs are kept in `tests/browser/baseline/phase0/` as the durable "before";
running shots land in the git-ignored `tests/browser/shots/`.

## Result

`bundle_viz.py --check` reported the constant already up to date against the
freshly split sources — **the move is byte-identical**, which was this phase's
acceptance test. `viz --dev` and the bundled path emit the same file
(`test_viz_dev_flag_matches_bundled_output`).

Tests: 123 pass (was 117; +6 — bundle sync, dev-path equality, deep-link aliases,
and three browser tests). Checker: 0 violations.

**The measured baseline confirms the diagnosis, in numbers rather than adjectives.**
Fit zoom and world bounding box per view, on the frozen 39/12 graph at 1440×900:

| view | fit zoom | world box | shape |
| --- | --- | --- | --- |
| Timeline | **0.183** | 847 × 4121 | 1:4.9 vertical ribbon, 160 labels at 18% |
| Frontier | **0.283** | 3295 × 201 | 1:16 flat bar in an empty screen |
| Provenance | **0.208** | 1028 × 3600 | 234 edges over 51 nodes |
| Clusters | 0.877 | 480 × 805 | 12 blobs, **0 labels** — unlabelled by design |

Three of four views fit below 0.29. Nothing at those zooms is legible, which is
the defect the next phases exist to fix. The one view that fits well draws no
labels at all.

Two follow-ups deliberately deferred rather than done here:

1. **The IIFE wrapper.** The target structure wraps the concatenated JS in one
   IIFE. Doing that now would have broken byte-identity, which was the whole
   acceptance test. It lands in Phase 1, where the JS changes anyway.
2. **`js/quadtree.js`, `js/layout-timeline.js`, `js/layout-board.js`** are not
   created yet — an empty file would be noise. They arrive with the phases that
   need them (1 and 6).

One addition to the planned structure: **`js/boot.js`**. The boot block sits after
the export handlers in the original source order, so folding it into
`controls.js` would have reordered the concatenation and broken byte-identity.
It is a real seam anyway — deep-link handling and first paint.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: hg-viz
- commit: 3276bd9f651c0ff163c229a31c3e5db4ea74c113

## State Impact

- target: polished-pond-2718 — viz sources split out of the single-file script and bundled back at build time: `tools/viz/` (index.html skeleton + viz.css + 9 JS parts + manifest.json) is now the authored form, `tools/bundle_viz.py` concatenates it into the `VIZ_TEMPLATE` constant, and `viz --dev` reads the sources straight off disk for the edit loop. Both hard properties are preserved and now tested: hypergraph.py stays one copyable file, and the emitted page stays self-contained. The move is byte-identical (`bundle_viz.py --check` clean against freshly split sources), so nothing about the rendered output changed. `assemble_viz_template()` lives in hypergraph.py and the bundler imports it, so the dev path and the constant cannot drift; `test_viz_bundle_in_sync` fails if the sources are edited without rebundling. Views renamed after their job — Timeline/Frontier/Provenance/Clusters — with the pre-rename hashes (#record #state #combo #combination #hyper) kept as aliases. A Playwright harness (dev group only, self-skipping) now measures every view in chromium against `tools/fixtures/self/`, a frozen 39-record/12-state snapshot of this repo's own graph. Its first baseline quantifies the defect: fit zoom 0.183 (Timeline, 847x4121), 0.283 (Frontier, 3295x201), 0.208 (Provenance, 234 edges over 51 nodes), 0.877 (Clusters, but 0 labels drawn). Tests 117 -> 123, checker 0 violations.
