---
node_id: 19246d0d-5c62-5ad9-979e-0e887a2b9627
slug: round-arrow-5061
title: 'hypergraph-viz attached: the export contract''s consumer exists, with a one-command attach/detach'
created_at: '2026-08-30T11:30:55+00:00'
parents:
- bold-sand-5009
summary: ''
---
## What

The planned consumer of the visualization seam exists and is attached. `hypergraph-viz` (`~/hypergraph-viz`, separate repo) is a live excaligraph-based viewer — record/state modes, fold/unfold, hyperedge blobs over the record graph, tune panel, SVG export — and it now reads this protocol's pinned JSON export contract through a new stdlib-only adapter, `make-viz-data.py`, with a one-command attach and a one-command detach.

## Why

`polished-pond-2718` is `open` for exactly one reason: "the capability is currently a contract whose consumer does not exist yet." The consumer does exist — it had simply never been connected, and this repo's graph did not know about it. Operator directive this session: verify the viewer, wire the integration, and make attach/detach easy so the two repos can be joined or separated at will. The contract side was already done: the export probe and baseline landed at zero findings [rec: bold-sand-5009], so the adapter codes against measured shapes, not prose.

## Method

Inspected the viewer first. It is a private vite app (`app.js` + `lib/`, no framework deps) whose data surface is five module exports: `RECORD_EDGES`/`RECORD_LABELS`, `STATE_EDGES`/`STATE_LABELS`, and `ASPECTS` — each aspect a state-node hyperedge listing its member record slugs. An uncommitted `app.js` diff already split the built-in demo from an optional drop-in `data.local.js` (via an eager glob import); the header of the stale `data.local.js` on disk named its generator, `make-viz-data.py`, but no such script existed in either repo, and the data was from a different project (myo).

Wrote the missing adapter, in the consumer's repo so core stays viz-free (the 0.1.0 gate removed even the stub [rec: steady-ember-8009]):

- **Input**: the contract only — `.hypergraph/cache/{record,state}.json`, located via a minimal read of the project's `config.yml` (`cache_dir:`). Missing exports produce an error naming `hypergraph export`, never a partial file.
- **Mapping**: `parent_ids` → `[parent_slug, child_slug]` edge pairs in `created_at` order; titles → labels truncated at 34 chars; each non-root state node's `[rec: slug]` body references → an `ASPECTS` entry (deduped, filtered to slugs present in the record export), hue/fill cycled from an Open Color palette matching the demo's.
- **Attach**: `python3 make-viz-data.py <project-root>` writes `data.local.js`. **Detach**: `--detach` removes it and the demo returns. The file is per-machine data, now gitignored.

Committed in hypergraph-viz as `4d2c3cc` (adapter + the app.js demo/local seam + README attach/detach section + .gitignore), on its `main`, not pushed.

## Result

Attached this project: **113 record nodes → 123 edges; 25 state nodes → 24 edges; 24 of 24 non-root state nodes resolved into aspects with 0 members dangling** (every `[rec:]` reference matched a record slug). Validated three ways: the generated module parses under node with all five exports well-formed; the vite dev server serves it at `localhost:5199`; and `npm run build` compiles the app with the data eagerly imported (✓ built in 64ms). Detach → attach round-trip verified.

The seam holds as designed: the integration surface is still exactly the JSON exports — core gained no viz code, the adapter lives with the consumer, and any other project attaches with one command. Not done here: the viewer has no notion of node *status* (frontier nodes are not visually distinct), and cross-repo provenance remains prose — both are viewer-side follow-ups, not contract changes. The code change itself lives in hypergraph-viz at `4d2c3cc`; the `## Repo` SHA below is this repo at recording time.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 628564207bc52f4ca628b3bf4c175711ab1c805a

## State Impact

- target: polished-pond-2718 — the consumer exists and is connected: hypergraph-viz renders both graphs from the pinned JSON exports via a stdlib adapter (make-viz-data.py, in the consumer repo); attach = one command against any project root, detach = removing data.local.js; verified against this project at 113/25 nodes, 24 aspects, 0 dangling members. Status open → working; the seam's remaining opens are viewer-side (status rendering) not contract-side.
