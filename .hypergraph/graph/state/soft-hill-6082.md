---
node_id: d3c43203-3cae-5de2-9a15-7c4d9b635384
slug: soft-hill-6082
title: State graph
created_at: '2026-08-14T13:25:57+00:00'
parents:
- young-wave-9364
summary: 'The live hypothesis: whether a distilled projection stays small and honest as evidence grows. Post-reorg shape measured (25 nodes, 128 KB, ~40% per-node cleanup; one-sitting still unmet); check rule still unbuilt.'
flywheel:
  node_id: 6b30c768-6c96-5b4b-83d3-bb22e3d17001
  slug: tiny-credit-9573
  revision: 1
  pushed_at: '2026-08-16T18:25:04+00:00'
  content_sha256: 275c18d204e1a6c297a3615e3b161378bcaf099d788bf6b824c6a9bb098931da
  parents_sha256: dc6b2502cf02e9c0a11edcb6ecfe3efdda6a9374782363c30835695dddc8b030
  parents:
  - 3310b4b6-38dc-5091-b321-0a62ce235f80
---
Status: open

## Current

The distilled half: what is true now, including the frontier of open, broken and blocked work. **This is the live hypothesis of the project and it is published as unproven** — the record graph is established practice, while the state graph and the cross-graph structure that falls out of it are the novel half, with *whether the projection stays small and honest as its evidence base grows without bound* named in public as the open research question [rec: clever-ledge-6588].

- **What is settled.** One writer (I3), so every state write goes through a reconcile pass; claims cite record slugs (I4); a status vocabulary whose open/broken/blocked members are the frontier (I6); negative knowledge carrying scope, confidence and evidence (I7) [rec: empty-cherry-5305]. Forward work is expressed as `open` nodes, which are gap-claims falsified by work through I2 rather than to-do items [rec: patient-limit-9007].
- **The open question is not rhetorical, and this repo is the counterexample.** Its own state graph reached **164 KB of node bodies across 16 nodes**, one of them 45 bullets, against SPEC's own convention that the whole state graph should be readable in one sitting. **Nothing detected it**, because size and shape are measured by nothing [rec: late-sage-5549].
- **The failure class is known and has bitten before**: an unmeasured category is invisible to every check by construction, which is how an adoption dropped 22 tags off 188 of 189 nodes without a word [rec: fresh-spire-9002].
- **Depth was not even expressible until now.** The graph was flat partly because a state node could not be re-parented — `push` emitted no mirror op at all for a pure re-parent, and `verify` could not see topology drift by default. Both are closed [rec: autumn-glade-5802], which is what let this graph take the shape it now has [rec: late-sage-5549].
- **The post-reorganization shape is now measured, and the first dispatch measured it** [rec: idle-crow-3832]: 25 nodes, 128.4 KB of bodies, max node 11.9 KB / 40 bullets, depth ≤ 2, frontier 5/25. Every pre-reorg offender shrank ~40% against the 164 KB / 16-node baseline — but a whole-graph read is still ~101 minutes at 200 wpm, so the one-sitting convention is still unmet. The measured envelope (body ≤ 12 KB, ≤ 40 bullets per node) is a candidate threshold set for the deferred check rule: it passes today's graph and would have flagged four pre-reorg nodes.
- **Deliberately not built yet**: a `check` rule for state-graph size and shape, and a SPEC convention stating what a good state graph looks like. This round reorganized this repo's own graph first, as evidence rather than assertion; generalizing it is the next round and now has numbers to generalize from [rec: late-sage-5549] [rec: idle-crow-3832].

## Negative knowledge

- [scope: distilled projections over an unbounded record | confidence: high | evidence: late-sage-5549 | decision: late-sage-5549] a convention stated in prose and measured by nothing is not a constraint. SPEC said the whole state graph should be readable in one sitting; this project's own reached 164 KB across 16 nodes, one node at 45 bullets, and every check passed throughout — because size and shape are not a category any invariant reads.

## Provenance

- clever-ledge-6588 — the state graph published as the novel, unproven half, with the open research question named
- empty-cherry-5305 — the invariants and template this half is written against
- patient-limit-9007 — open nodes as gap-claims rather than to-do items
- late-sage-5549 — the 164 KB measurement, the reorganization, and the deferral of the generalizable half
- fresh-spire-9002 — the failure class: an unmeasured category is invisible to every check
- autumn-glade-5802 — re-parenting closed, which is what made depth expressible
- idle-crow-3832 — the first dispatch's unit: post-reorg shape measured, thresholds proposed
