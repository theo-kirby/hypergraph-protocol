---
node_id: 94d8c624-d70b-56ac-956f-ec9b5a944540
slug: wandering-crane-1698
title: Record graph
created_at: '2026-08-14T13:25:56+00:00'
parents:
- young-wave-9364
summary: 'The append-only half: one causally-parented markdown file per unit of work, immutable in body and in topology, merging without conflict, and the only place evidence hangs. The mature half of the protocol.'
flywheel:
  node_id: 3cab6d40-ec5e-53a3-a7b7-eddaa1a9ab05
  slug: broad-sun-1795
  revision: 0
  pushed_at: '2026-08-14T13:37:08+00:00'
  content_sha256: 8521b4295a3edf43bdca6088749321d7c4700ed4dee33b568e0dcef05fe8bda6
  parents_sha256: dc6b2502cf02e9c0a11edcb6ecfe3efdda6a9374782363c30835695dddc8b030
  parents:
  - 3310b4b6-38dc-5091-b321-0a62ce235f80
---
Status: working

## Current

The append-only half: everything that happened, one markdown file per node, causally parented [rec: spring-pine-7256]. It is the **mature** half of the protocol and is published as such — an append-only causal log is a lab notebook under another name [rec: clever-ledge-6588].

- **Every unit of work is one node**, carrying `## What / ## Why / ## Method / ## Result / ## Repo / ## State Impact` at exact checker-parseable headings, with I2 requiring the impact declaration on every one of them [rec: empty-cherry-5305].
- **Immutability is exercised, not merely asserted.** A wrong figure in a committed node was corrected by a **child node** rather than an edit, and reconcile folded the corrected value [rec: sleepy-branch-3744]. `hypergraph update` refuses record nodes outright, and a test asserts that refusal was not weakened when `artifacts:` became editable [rec: shady-bay-7654].
- **`artifacts:` is the one editable frontmatter key**, and only because the append-only hash covers the **body**: `LocalNode.sha256` hashes content alone, so the command cannot reach the title, the summary or the body [rec: shady-bay-7654].
- **The parent edge is causal history and does not move either.** `hypergraph update --parent` is state-only, and `push` refuses to mirror a stamped record node whose parent set changed [rec: autumn-glade-5802].
- **One file per node is what makes the graph merge.** Two branches produce two new files and merge with zero conflicts, always — which is why recording is safe on any branch, fork or machine, and why a slug collision surfaces as a loud git add/add conflict rather than silently, since `node_id = uuid5(slug)` makes a silent collision an identity collision [rec: vast-rain-4873].
- **Evidence hangs here and nowhere else.** A record node enumerates the files its claims rest on; a state node reaches them in one hop through `## Provenance`, and `artifacts:` on a state node is a `check` violation [rec: shady-bay-7654].

## Negative knowledge

None yet.

## Provenance

- spring-pine-7256 — the record-first design this half encodes
- empty-cherry-5305 — the record-node template and I2
- sleepy-branch-3744 — correction-by-child-node exercised in practice
- shady-bay-7654 — artifacts: as the one editable frontmatter key, and evidence on record nodes only
- autumn-glade-5802 — record topology refused as a mirror write, alongside state re-parenting
- vast-rain-4873 — what git already provides: conflict-free merges and loud slug collisions
- clever-ledge-6588 — the record graph published as the mature half
