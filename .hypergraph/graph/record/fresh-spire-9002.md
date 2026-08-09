---
node_id: 867ab4b2-7b90-5e64-ac74-84b33ec6c8f4
slug: fresh-spire-9002
title: 'Tags did not travel: 22 of them, and Flywheel could carry every one'
created_at: '2026-08-09T22:32:02+00:00'
parents:
- clever-ledge-6588
summary: neural-whoop's import --fork carried 189 nodes and none of the 22 tags on 188 of them, including a 6-hop `★ studio-baseline` pointer chain whose hops record when but never why. Flywheel has implemented op 10 all along (create/assign/update/delete), so the loss was avoidable; SPEC's "the shipped storage does not implement" is true only of the local adapter.
---
## What

Field audit of what the neural-whoop adoption (2026-08-09) dropped on the floor.
`import --fork` carried 189 nodes with their topology, titles, bodies, summaries and
archive identities. It carried **no tags**, because the protocol has no tag concept —
and the loss was avoidable, because the backend has had the operations all along.

## Why

SPEC.md line 409 files tags under "Future work" as "op 10, which the shipped storage
does not implement". That sentence has been read as *the backend cannot do this*. It
is only true of the local adapter. Flywheel, the one hosted backend this project
mirrors to, implements the whole op: create, assign, update, delete. So the adoption
path threw away data that both ends could represent, and nothing reported it.

This matters beyond one repo. Adoption is the protocol's claim that a project with a
past can come under it without losing the past. Every category of thing that silently
does not travel is a counter-example to that claim, and the honest way to count them
is to measure a real adoption rather than reason about the code.

## Method

Read `/Users/theo/neural-whoop/.hypergraph/cache/mirror-pull.json` — the 189-node
export the adoption imported from — and counted the tag structure directly. Confirmed
Flywheel's tag surface from `flywheel help` rather than from memory.

## Result

**The vocabulary: 22 tags**, all defined on the graph root
(`morning-feather-7342`, `neural-whoop: GPU-parallel, swarm-capable whoop RL lab`).

| family | count | examples |
| --- | --- | --- |
| `kind:*` | 5 | `kind:experiment`, `kind:measurement`, `kind:method`, `kind:idea`, `kind:hypothesis` |
| `outcome:*` | 3 | `outcome:GREEN`, `outcome:RED`, `outcome:NO-GO` |
| `cluster:*` | 11 | `cluster:reward-shaping`, `cluster:swarm`, `cluster:perception`, … |
| `topic:*` | 1 | `topic:pufferlib` |
| `★` pointer | 2 | `★ studio-baseline`, `★ airframe-of-record` |

Each tag carries `tag_id`, `name`, `bg_color`, `text_color`, `one_only`,
`track_history` (and a server-side `history_next_index`).

**Assignment: 188 of 189 nodes** carry a non-empty `tag_ids`, 1–6 each. Only the root
itself is untagged.

**The root's copy is authoritative, and a union is still necessary.** Only 130 of the
189 nodes echo the vocabulary in their own `graph_tags`; 59 carry an empty list while
still carrying `tag_ids`. So resolving an id to a name from any single node's copy
fails on a third of the graph — the union across all nodes is required, and the
parentless node is the tie-breaker when copies disagree.

**Pointer tags move, and the moves are recorded.** `★ studio-baseline` is a
"current best" pointer with `one_only: true`, `track_history: true`, and a **6-hop
chain** reconstructable from per-node `tag_history` entries:

| hop | node | superseded_at |
| --- | --- | --- |
| 1 | `old-truth-3996` | 2026-06-28T15:35:12Z |
| 2 | `empty-firefly-1882` | 2026-06-28T16:15:05Z |
| 3 | `purple-base-8302` | 2026-06-28T21:29:28Z |
| 4 | `snowy-sun-6709` | 2026-07-03T14:55:05Z |
| 5 | `muddy-mouse-2952` | 2026-07-07T02:25:07Z |
| 6 | `broken-wildflower-8398` | 2026-07-13T21:24:23Z |

Each hop has a timestamp and a successor. **No hop has a reason.** That is the whole
epistemic content of the chain: six times someone decided the baseline had moved, and
six times the graph recorded *when* and not *why*. `★ airframe-of-record` sits at
`history_next_index: 1` — declared with history tracking on, never moved.

**Flywheel implements op 10 in full**, confirmed from `flywheel help`:

| op | endpoint | optimistic lock |
| --- | --- | --- |
| `tags:create` | `POST /nodes/{root_node_id}/tags` | root revision |
| `tags:assign` | `PUT /nodes/{node_id}/tags` — atomic replace | node revision |
| `tags:update` | `PATCH /nodes/{root_node_id}/tags/{tag_id}` | root revision |
| `tags:delete` | `DELETE /nodes/{root_node_id}/tags/{tag_id}` | root revision |

Two properties fall out that any implementation has to respect. `tags:assign` is an
**atomic replace**, not an add — so it cannot duplicate, and it bumps the *node*
revision. `tags:create` bumps the *root* revision on every call, so a root revision
read once and reused across a 22-tag creation loop is wrong after the first tag.

**There is no `tags:list`.** The vocabulary is read back through
`nodes:get --projection full` and its `graph_tags` key. An absent key there must raise
rather than read as "no tags" — the difference is between a no-op and re-creating the
entire vocabulary.

## Assessment

The loss is real, measured, and repairable in both directions: forward, by teaching
`import` and `push` about tags; backward, by a repair pass over a repo that adopted
before the capability existed. neural-whoop can run the backward half **offline
today** — `mirror-pull.json` already holds all 189 nodes with their `graph_tags` and
`tag_ids`, so no network read is needed to recover the names.

What cannot be recovered is the *reason* for any of the six baseline moves. It was
never written down on the source graph either. That is a finding about pointer tags
as a construct, not about the import: a moving pointer with no reason is a claim the
graph cannot audit.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: e2a69818add5f9a8f24576d7af8ff18f46bacc6a

## State Impact

- target: bitter-sound-9744 — Second field measurement of what adoption drops: 22 tags across 188 of 189 neural-whoop nodes, plus a 6-hop pointer chain. Measured, not inferred.
- target: blue-sun-8921 — Op 10 (tags) is not a future operation: Flywheel implements create/assign/update/delete today. Only the local adapter does not, and INTERFACE.md says otherwise.
- target: morning-crane-7863 — Adoption's known-loss list is understated: it names artifacts, not tag taxonomies. import --fork drops tags silently.
