---
node_id: 53e214e5-6bda-50a8-bce7-06f9bb25d5e7
slug: tiny-stone-3934
title: 'Viz: everything by default, drag-stable blobs, tuning sliders, arrange buttons'
created_at: '2026-08-09T17:19:00+00:00'
parents:
- wise-river-3571
- humble-rain-0304
summary: ''
flywheel:
  node_id: b4fc6cdd-7638-54ae-8e8b-4cd15ee4221f
  slug: orange-violet-0977
  revision: 0
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: 8f02fcd7e57beefcce9145d864e31ebda516ce1fa8a7ed88d6063bc08aaa8298
  parents_sha256: bd029180df71b3dfadb402e22b748887ee2a0c58d01d5f2307c09422cb4ec4de
  parents:
  - f6b6de60-6126-5155-b7c0-3213b995beb2
  - c8d4ea51-4515-51b0-afee-cb897c419377
---
## What

Five changes to the viz page, from five complaints about using it:

1. **The page boots into Everything.** A fifth preset — `graphs: both`, circles,
   force, `links: all`, all four checkboxes on — added last in `PRESETS` and made
   `boot.js`'s fallback. The `show` literal was moved to the same values so the two
   cannot disagree. Deep link `#everything`, number key `5`.
2. **A drag keeps the real blob shape.** `blobFieldMode()` no longer falls back to
   the convex hull while dragging; it is now purely the zoom test. A drag stays on
   the distance field and pays for the frame rate with a coarser sampling grid
   (`BLOB.dragCoarsen`, 2.5x pitch ≈ 1/6 the samples), a relaxed point budget, and
   one recompute per animation frame instead of one per pointermove.
3. **Eleven blob tuning sliders**, in a collapsed `<details>` in the sidebar —
   padding, corridor, smoothing, clearance, resolution, tolerance, maxPoints,
   dragCoarsen, fillOpacity, strokeWidth, labelSize. Each row shows the live value,
   marks itself when moved off the default, and carries a one-line hint. Reset and
   Copy-as-YAML alongside.
4. **A `viz: blob:` block in `.hypergraph/config.yml`** carries a tuning with the
   repo. Precedence: hard defaults → config → localStorage → live slider; Reset
   drops the browser's copy and returns to the config.
5. **An Arrange row** — Spread, Tighten, Shuffle, Relax, Reset.

## Why

Follows `wise-river-3571`, which landed the four-view overhaul, on top of the
0.0.7 tree (`humble-rain-0304`).

The four views were each a deliberate slice, and the page opened on the narrowest
of them. That is the right default for a *reader* who knows what they want and the
wrong one for anyone meeting the graph: you cannot pick a slice of something you
have not seen. Everything-first inverts it, and costs nothing — the four focused
views are one click or one number key away.

The drag was the real defect. `controls.js` set `blobDragging = true` on every
pointermove and `blobFieldMode()` returned the convex hull for it — hull padding is
`R + BPAD` = 34px with no corridor, no concavity and no non-member subtraction, so
touching a node replaced a traced outline with a much larger blob. It was a
deliberate speed trade ("the distance field is too costly per frame") but it reads
as breakage, and it was buying a frame rate the field can supply anyway at a
coarser pitch.

Sliders and a config block, rather than tuned constants, because the right values
are a judgement about *this* graph at *this* density — and a judgement is worth
committing once it is made.

## Method

Three latent bugs sat behind the drag change and had to be fixed first, or the
release-quality redraw on pointerup would hand back stale geometry. All three are
the same bug: positions are mutated **in place**, so nothing in any cache key
changes when a node moves.

- `avoidGrid`'s key was node count + `layoutKey()` — a node dragged into a cluster
  never became an obstacle for it.
- `blobCache`'s key was the state slug + rounded **member** positions — dragging a
  **non-member** through a blob left the key identical, so pointerup restored the
  pre-drag outline.
- `updateBlobs` repainted only `memberOf[slug]`, so a non-member entering a blob
  changed nothing on screen.

Fixed with one mechanism: `let posEpoch = 0` in core.js, incremented once per drag
frame and once per Arrange action, folded into both cache keys. Pan, zoom and
checkbox flips do not touch it, so caching still works everywhere it did before.
`updateBlobs` now repaints `memberOf[slug]` ∪ the blobs whose member bounding box
is within avoid reach of the node (`blobsTouching`).

One performance trap found while doing it: `blobLabelPositions` calls
`blobGeometry` for **every** hyperedge to anchor labels on outlines. With the field
now live during a drag and `posEpoch` defeating the cache, that would have computed
14 fields per frame to place labels that are not moving. A drag now anchors on each
blob's last-known geometry (`labelLoops`); pointerup redraws the layer exactly.

Also fixed: `hashSlug` was defined **twice** with identical bodies (core.js and
layout-force.js). Both are hoisted declarations in one IIFE, so the later one in
manifest order silently won. Deleted the layout-force copy; the surviving one takes
the shuffle seed — `forceSeed ? s + "#" + forceSeed : s`, so seed 0 hashes
byte-for-byte as before and **the default layout does not move**. Shuffle walks
1, 2, 3…, so the page stays fully deterministic and an exported SVG reproducible.
The seed is appended to `layoutKey()`, not to `show` — a new `show` key would break
`activePreset()`, which compares every key against each preset.

Two design corrections came out of testing rather than planning:

- **Shuffle is one-way**, so a shuffled arrangement was a door that shut behind you.
  Reset now returns the seed to 0 as well as recomputing, which makes every earlier
  arrangement reachable again: reset, then shuffle twice, and you are back at seed 2
  exactly.
- **Relax was reheating, not settling.** The full layout runs 240 ticks from alpha 1
  and ends cold near 0.03; relaxing from 0.35 kicked an already-settled drawing.
  Dropped to 0.15 over 90 ticks, landing where the full sim lands. Unclustered nodes
  are also anchored at their current position (weight 0.06) instead of taking the
  sim's slow pull toward the origin, which over 90 ticks walked a far-out node a few
  hundred px — the opposite of "keeps your drags".

New `tools/viz/js/tuning.js` (manifest: after blob.js, before render.js). The three
style knobs were literals in `drawBlobs` and were lifted into `BLOB`; dark mode's
+4 opacity lift is kept as an offset from the one knob. `build_viz_data` gained
`settings.blob` from `config["viz"]["blob"]` — `load_config` already parses YAML,
so no new dependency and no Python version bump. `live.js`'s `adoptData` already
left `DATA.settings` alone; that is now commented as deliberate.

Verification. `uv run pytest tests/` — 311 passed, 1 skipped (was 307). Four new
tests in `tests/test_viz.py`: the boot preset and five arrange button ids; the
tuning panel and every slider key being a real `BLOB` field; `blobFieldMode` having
dropped the drag term and `posEpoch` reaching the caches; and `settings.blob`
surfacing a config block and defaulting to `{}`. `tests/browser/test_scale.py` was
updated — first paint at 500 nodes is now the Everything view (560 nodes drawn, not
500), which is the heaviest thing the page draws and a better guard than the old
single-graph default.

Beyond the suite, a 30-check Playwright script drove the real page against this
repo's own graph (62 record / 15 state / 15 blobs / 297 ribbons), measured through
the DOM only — the page wraps itself in an IIFE and there are deliberately no
test-only hooks in it, so hyperedge membership was recomputed from the same payload
the page received. Scratch script, not committed.

## Result

All 30 browser checks pass, no console errors.

- **Boot** — chip Everything, `both/circles/force/all`, all four boxes checked and
  none disabled, Links segment visible.
- **Drag a member** (`wandering-sun-8831`, 18 members): curve segments before 208,
  mid-drag **128**, after release **208**. Under the old behaviour mid-drag was the
  hull. 128/208 is the coarse grid, not a different shape.
- **Drag a non-member** into that cluster's centre: the outline changes
  (208 → 207 segments, different path) — the field bends around it. This is the
  case that silently did nothing before.
- **Sliders** — 11 rows; `padding: 40` redraws live and marks itself
  (`class="value changed"`); `strokeWidth: 4` reaches the drawn `stroke-width`
  attribute; the tuning persists to `localStorage` and across a reload; Reset
  restores the geometry, clears the store and clears the marks; Copy reports back.
- **Config** — a page built from a config carrying
  `padding: 26, smoothing: 34, strokeWidth: 2.5` starts its sliders there, leaves
  unset keys at their defaults, treats the configured values as the baseline (no
  "moved" marks), draws `stroke-width="2.5"`, lets a live edit outrank and outlive
  it, and **Reset returns to the config, not to the hard default**.
- **Arrange** — Spread 953 → 1096px span, Tighten back to 953; Shuffle differs, a
  second Shuffle differs again, Reset returns to the original layout exactly, and
  shuffle-reset-shuffle-shuffle reproduces seed 2 byte-for-byte; Relax changes the
  arrangement with a largest move of 214px on a ~950px layout (a global contraction,
  structure intact); Shuffle and Relax hide outside the force layout and come back.

Docs: README gains the fifth view, the Arrange paragraph, the `#everything` deep
link and the full `viz: blob:` block with per-key comments; SPEC's tooling paragraph
notes the everything-on default and says the block is display configuration no
invariant reads; `.hypergraph/config.yml` carries a commented example, deliberately
not an active block — this project's page runs on the shipped defaults and a block
pinning them would only go stale.

Out of scope, unchanged from the plan: `viz.toml`. The CLI parses no TOML,
`requires-python` is `>=3.10` and `tomllib` is 3.11+, so a second config file costs
a `tomli` dependency or a version bump. The `viz:` block reuses `load_config` and
travels in the file that is already there.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 94ac1c9eaa56aa10db153e23ced2a9beeee397b2

## State Impact

- target: polished-pond-2718 — Fifth view Everything is now the default boot view (both graphs, circles, force, links all, all four edge toggles on); the four focused views stay one click or number key away. Dragging a node keeps the traced distance field instead of falling back to the convex hull — the grid coarsens by BLOB.dragCoarsen and the repaint is throttled to one animation frame. Three position-cache bugs fixed behind it (avoidGrid, blobCache and updateBlobs all missed in-place position changes), via a posEpoch counter folded into both cache keys. Eleven live blob tuning sliders in the sidebar, persisted to localStorage and copyable as YAML. A new optional 'viz: blob:' block in .hypergraph/config.yml presets them, so a tuning travels with the repo: defaults -> config -> localStorage -> live slider, with Reset returning to the config. An Arrange row (Spread/Tighten/Shuffle/Relax/Reset) moves the whole drawing; Shuffle uses a seed counter appended to layoutKey, so the page stays deterministic and seed 0 hashes identically to before — the default layout does not move. The duplicate hashSlug definition (core.js and layout-force.js, later one silently winning) is gone.
