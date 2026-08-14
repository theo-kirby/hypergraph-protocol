---
node_id: c3fdd01f-47ce-55ad-8ead-8ba6a64bc609
slug: still-forest-9161
title: 'Viz UI overhaul: tabs collapsed into unified toggle-driven view with presets'
created_at: '2026-08-07T13:55:27.071507+00:00'
parents:
- morning-rain-7488
summary: Four viz tabs replaced by one view driven by display toggles plus preset chips Record/State/Columns/Force; slim icon header, sidebar controls, resizable divider.
flywheel:
  node_id: c3fdd01f-47ce-55ad-8ead-8ba6a64bc609
  slug: still-forest-9161
  revision: 0
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: 2d7e835c034e5b7ba8530b0a1169fca4da582bba1e4f7d339f281f262e0df5cc
  parents_sha256: 8e27e131262985ce30b35a404b3ed0817727367435268884d5a891a9ccdd3f89
  parents:
  - 27fef7d4-de86-570b-9722-68d715b0eac1
---
## What

Collapsed the viz page's four tabbed views (Record / State / Combination / Hypergraph) into one unified view driven by display toggles — graph visibility (record | state | both), node style (cards | circles), layout (layered | force, independent of style), and per-species edge toggles (parent edges, impact links, provenance links, hyperedge blobs). Preset chips reproduce the old arrangements under arrangement-based names: Record, State, Columns, Force ("Combination" was a mislabel — every arrangement is a hypergraph presentation). Chrome redesigned: header slimmed to title + icon buttons (fit, theme with sun/moon swap, export dropdown for SVG/PDF); search moved into the sidebar above a new Display section; header + sidebar render as one continuous surface with an inverse-rounded corner where the canvas insets; sidebar resizable (drag) and collapsible (click) via a 7px divider.

## Why

Operator direction after using the four-tab page: the tabs were four fixed points in what is really a toggle space (useful mixes like both-graphs-with-blobs or cards-under-force were unreachable), and Combination's name misrepresented the model. Confirmed decisions: presets + toggles (not toggles-only); layout independent of node style; impact and provenance as separate edge toggles.

## Method

All work in the VIZ_TEMPLATE of tools/hypergraph.py; the Python data layer (build_viz_data, layered_layout, render_viz) needed zero changes. A `show` state object replaces `let view`; positions/pan/fit caches rekeyed by layout signature (layout:graphs:style) with edge/blob toggles deliberately excluded so checkbox flips never reset pan/zoom or node drags. Force sim generalized: springs derived from graph structure (record + state parent edges k=0.03 rest=110; cross-links k=0.012 rest=170 when both graphs visible), state slugs appended to hyperedge cohesion clusters; cards under force get a deterministic anisotropic post-scale (x3.2, y1.8) plus a bounded axis-choice de-overlap pass (needed — the scale alone left overlapping cards with 21 nodes). Blob hulls expand card members to their four corners before convexHull. Deep links #record/#state/#combo/#combination/#hyper map to presets; #<slug> jumps, switching graph visibility to both when the target is hidden. Determinism preserved (FNV hash seeding only, no Math.random); DATA payload line and test-coupled identifiers (convexHull, blobPath, runSim, hyperedges) untouched.

## Result

22/22 pytest green (test_template_has_four_views replaced by test_template_preset_toggle_machinery; count unchanged); checker clean. Headless-browser smoke test (Playwright, 24 checks): every preset chip reproduces its old arrangement exactly; custom mixes render (both+force+blobs, cards+force with zero card overlap); edge-checkbox flips preserve pan and drop only their edge species; all five hash deep links land; divider click-collapse/drag-resize, theme icon swap, export menu, and SVG download (named <project>-<preset|custom>.svg) all verified. README and SPEC updated to describe the unified view.

## Repo

- repo: https://github.com/theo-kirby/hypergraph
- branch: main
- commit: 1ec613358ceac7e561cc6deb09a86de6a9454606

## State Impact

- target: polished-pond-2718 — viz is now a single toggle-driven view (graphs/style/layout/edge toggles) with preset chips Record/State/Columns/Force replacing the four tabs; resizable sidebar, icon header with export menu; deep links preserved including the #combination alias