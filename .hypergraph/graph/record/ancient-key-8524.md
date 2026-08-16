---
node_id: 4e73be98-bef1-5873-9957-9c341f28f872
slug: ancient-key-8524
title: 'Dispatch: within cool-king-8586'
created_at: '2026-08-16T18:16:05+00:00'
parents:
- loyal-tide-3608
summary: 'Lane claim for falling-glacier-9058: region dispatch at the state root chose polished-pond-2718 (Visualization), avoiding the unreconciled even-journey-4120 claim on soft-hill-6082; budget 1 unit.'
---
## What

Opened dispatch lane `falling-glacier-9058` at the region target `within
cool-king-8586` (the state root), budget 1 unit. Oriented over the subtree, read
the live claims, and chose **`polished-pond-2718` (Visualization)** as the node to
work. This node is the lane claim; the unit of work follows as its child.

## Why

Causal parent: `loyal-tide-3608`, the provenance of the chosen target — the viz
cut, the node that removed visualization from core and declared the JSON exports
(`.hypergraph/cache/{record,state}.json`) the whole integration contract.

**Avoided claim, named explicitly**: the unreconciled dispatch lineage
`even-journey-4120` (`Dispatch: within cool-king-8586`, lane
`weathered-eagle-6214`), closed by its child `idle-crow-3832`, already worked
**`soft-hill-6082` (State graph)** in this same region. That lineage is closed but
not yet reconciled: its impacts on `soft-hill-6082` (and `wandering-sun-8831`)
have landed in the record graph, but STATE.md still shows the target as if
unworked. Across the reconcile gap the target is taken — working it again would
duplicate the post-reorg shape measurement.

The region's remaining open descendants, per the region grammar:

- **`polished-pond-2718` (Visualization) — chosen.** The node is open because "the
  capability is currently a contract whose consumer does not exist yet". The
  contract itself lives only in prose (backend/local-adapter.md names the exports
  as the integration surface); no committed evidence pins down what shape those
  exports actually have. One unit that measures the export contract — observed
  keys, types, optionality, referential integrity — gives the planned consumer
  (hypergraph-viz) an empirical baseline and gives future changes something to
  drift against. `even-journey-4120` rejected this node only for *rebuilding* the
  visualizer, which is larger than one unit; pinning the contract is not.
- `soft-hill-6082` (State graph) — taken by the unreconciled `even-journey-4120`
  lineage, as above.
- `weathered-union-7494` (Announcement) — parked by Operator directive
  [rec: southern-ridge-1802]; venue and wording are the Operator's call.
- `protocol-benchmark-4417` (Protocol benchmark) — parked by the same Operator
  directive; nothing spends until the Operator resumes.
- `hollow-rain-8997` (Autonomous operation) — the missing evidence is a multi-loop
  unattended run, which does not fit a 1-unit budget honestly.

## Method

The hypergraph-dispatch skill, steps 1–4: read STATE.md; checked claims via
`hypergraph hwm` (11 unreconciled nodes, among them the `even-journey-4120`
dispatch lineage), `grep -l "^title: 'Dispatch:" .hypergraph/graph/record/`, and
`hypergraph dispatch ls` (no lanes, no live claims — the prior lineage is closed,
but unreconciled and therefore still a taken target); opened the lane with
`hypergraph dispatch open --at "within cool-king-8586" --budget 1`; recorded this
claim node in the lane before any work.

## Result

Lane claim recorded on branch `lane/falling-glacier-9058`. Budget: 1 unit, to be
spent on a reproducible measurement of the JSON-export contract
(`.hypergraph/cache/{record,state}.json`) as evidence toward the seam
`polished-pond-2718` holds open. State changes only when work lands.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: lane/falling-glacier-9058
- commit: fd8c5751e31c732ebde9ded2662011dd7b7feed2

## State Impact

none: lane claim — dispatched at within cool-king-8586; state changes when work lands
