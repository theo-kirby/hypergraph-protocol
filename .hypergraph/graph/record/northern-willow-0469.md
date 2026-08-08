---
node_id: 97345c89-4118-5e18-8b82-7abf6ab5ec8a
slug: northern-willow-0469
title: 'a3go re-mirrored: full 108-node history under our own roots, verify clean against the mirror alone'
created_at: '2026-08-08T11:32:18+00:00'
parents:
- tender-moss-3792
summary: ''
flywheel:
  node_id: b308e1a7-ee5f-52c4-979d-fa39f253873b
  slug: aged-shape-0444
  revision: 0
  pushed_at: '2026-08-08T11:35:36+00:00'
  content_sha256: 041d225cc92449f7e198bae35b9f92514be804e3bd57f42f817beaefd85bb55e
---
## What

Migrated a3go to fork-import, live. Its Flywheel mirror now carries the whole
108-node imported history under roots this account owns, with the original topology,
a lineage pointer at the record root, and — for the first time on an adopted project —
`push --verify` exit 0 against the mirror roots **alone**.

Measured before and after, `flywheel export:subgraph` over a3go's two mirror roots
with no archive anchors:

| graph | before | after |
| --- | --- | --- |
| record | 4 (root, epoch marker, 1 post-epoch record, legend) | **112** |
| state | 9 | 9 |

## Why

Executes M3 of the fork-import plan recorded in `copper-moss-3669`, using the tooling
shipped in `tender-moss-3792`. a3go is the mode-A dogfooding target and the project the
defect was measured on.

## Method

Repo `theo-kirby/a3go`, cloned fresh; the dev CLI run out of this checkout. Steps as
planned, with the deviations noted under Result.

1. Confirmed the diagnosis live: `flywheel nodes:get` on the archive root
   `73d510e5-…` returns `can_write: false` — the archive really is not ours. A mirror
   export over `e20a09e8-…` alone returned **4** record nodes.
2. `flywheel export:subgraph --node_ids 73d510e5-…,f9f2bf74-… --include_descendants`
   → 108 nodes.
3. `hypergraph import --record archive.json --fork --force` → rewrote 108 node files.
   Each swapped `flywheel:` for `origin:` and nothing else: 324 insertions, 324
   deletions across 108 files. The epoch marker and the post-epoch record node are
   absent from the archive export, so `--force` could not touch them — confirmed by
   diff.
4. `hypergraph check` → **0 violations, 0 warnings**, 107 pre-epoch nodes I2-exempt.
   `origin:` is inert to the checker, as designed.
5. `hypergraph push --plan` → **108 creates, 0 updates** (below the 200 warn
   threshold, so no scale warning — correct).
6. Executed the plan with a driver script: `flywheel nodes:commit-new` per op in plan
   order, parents resolved from ids minted earlier in the same run, the parentless
   local record root `purple-fog-6345` parented to the mirror record root
   `lively-feather-9068`. Paced at 0.55 s/create to stay under 120 creates/min.
   `push --record-result` after every 20 creates. **108 created, 108 recorded, zero
   429s, zero retries.** Re-planning afterwards gave 0 creates, 0 updates.
7. Re-parented the epoch marker: `flywheel nodes:add-parent` attaching
   `rough-poetry-7791` (the mirror copy of `crimson-rice-4497`), then
   `nodes:remove-parent` dropping the mirror root. Proved on this one node before
   trusting it, as planned.
8. Mirror record root: lease → commit → release. Title `a3go — record (hypergraph
   mirror)` → `a3go — record`; body replaced with `hypergraph push --lineage` output,
   which names both archive roots with their titles, says the archive is frozen and
   never written to, and states that artifacts stayed behind.
9. `hypergraph push --legend` → 118 rows (110 record + 8 state diverged pairs);
   committed onto the existing legend node `rapid-forest-3577`.
10. Verified against `mirror-only.json` — an export of `e20a09e8-…` and `1d824823-…`
    with **no archive anchors**.
11. Committed and pushed a3go (`f803ba7`), 112 files changed.

## Result

**`push --verify` against the mirror roots alone: exit 0.** `hypergraph check`: 0
violations, 0 warnings. `push --plan`: 0 creates, 0 updates. Mirror totals: 112 record
nodes (108 legacy + marker + post-epoch record + root + legend, minus the local record
root that maps onto its own mirror node), 9 state nodes.

Three things the plan did not predict:

1. **A second node needed re-parenting.** The plan named only the epoch marker. A
   topology audit — every local node's parent slugs mapped through `flywheel:` ids and
   compared against the mirror's `incoming_ids` — found the post-epoch record node
   `icy-fjord-0022` also hanging off the mirror root, because *its* local parent
   `still-recipe-4954` was a legacy node absent from the mirror when it was first
   pushed. Same defect, same fix. After both repairs the audit reports **0 topology
   mismatches across all 119 local node files**. The audit is the generalizable part:
   re-parenting is needed wherever a node was mirrored before its true parent existed,
   not just at the epoch boundary.
2. **Re-parenting causes revision skew, and verify catches it.** The first
   mirror-only verify returned 4 DRIFT findings — `crimson-rice-4497`,
   `still-recipe-4954`, `lively-orchard-3365`, `icy-fjord-0022` — all "revision skew",
   no content drift. `add-parent`/`remove-parent` bump the revision on **both** ends of
   the edge, while the node files still recorded revision 0. Resolved by feeding the
   mirror's current revisions back through `push --record-result`. This is verify doing
   its job on a real edge case; the skill layer should expect it after any re-parent.
3. **`nodes:commit-new` requires `local_temp_node_id`.** Omitting it is a 422 with the
   payload rejected server-side, so nothing is created — safe, but it cost one failed
   attempt. The response nests identity under `node`: `{node: {node_id, slug_name,
   revision}}`.

Also corrected while here: a3go's `.hypergraph/AGENTS.md` said only that reconcile
"pushes to NEW mirror roots"; it now says the mirror carries the whole graph with
original topology, and that verification must use the `mirror_roots:` export alone
because adding archive anchors hides exactly this failure. The config `archive:` block
gained `title:` per root (needed by `push --lineage`), `imported: 108`, and
`artifacts: retained-on-archive`.

tbinn needs no migration: mode B, no `origin:`, already mirrors in full.

No record node was written in a3go itself. The change there is a mechanical re-stamp of
frontmatter plus mirror bookkeeping — the same category as its existing "Mirror push:
… stamped" commits, which are plain git commits with no record node. a3go's own memory
is unchanged in content; only its projection moved.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 1c5810ad7c47d37068b3e53422e254aa2d06bdc0

## State Impact

- target: bitter-sound-9744 — a3go's mirror went from 4 record nodes to 112: the whole imported history re-published under roots this account owns, original topology restored, lineage at the record root, push --verify exit 0 against the mirror roots alone (first genuine mirror check for an adopted project). tbinn unaffected (mode B)
- target: morning-crane-7863 — fork-import proven end to end in the field; mode-A adoption now mirrors in full. New knowledge: any node mirrored before its true parent existed needs re-parenting (two on a3go, not just the epoch marker), and re-parenting bumps revisions on both edge ends, which verify reports as revision skew until push --record-result resyncs
- target: blue-sun-8921 — new claim: flywheel nodes:commit-new requires local_temp_node_id (omitting it is a server-side 422, so nothing is created) and nests identity under node:{node_id,slug_name,revision}; nodes:add-parent/remove-parent verified live on two nodes, add-then-remove keeps the child parented throughout
