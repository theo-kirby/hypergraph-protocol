---
node_id: bb23c9ca-1452-5cb8-942b-024f1642fcf8
slug: copper-moss-3669
title: 'Decision: fork-import — adopted projects mirror their full history'
created_at: '2026-08-08T09:44:16+00:00'
parents:
- humble-clover-7048
summary: ''
flywheel:
  node_id: c03099f4-aca7-5760-8467-7f274d0498df
  slug: super-cloud-3842
  revision: 0
  pushed_at: '2026-08-08T11:35:36+00:00'
  content_sha256: 047fa90fff445f451e682c9a1cf66cec8e0be653ef68d0e6060ceff7e20295c6
---
## What

Opened a new thrust in the adoption milestone: **fork-import**. An adopted project must
re-publish its whole imported history to a mirror it owns, with the original topology
kept, and an archive-lineage pointer at the mirror root. This node records the
diagnosis and the design before any code is written (SPEC: Forward work).

The measurement that started it, taken live on a3go on 2026-08-08 with
`flywheel export:subgraph` over both mirror roots:

| graph | mirror nodes | expected |
| --- | --- | --- |
| record | **3** (root, epoch marker, one post-epoch record) | 111 |
| state | 9 (root + 8 components) | 9 |
| legend | 1 | 1 |

105 imported legacy nodes were never pushed to a3go's own mirror.

## Why

Follows from `humble-clover-7048` (M5: a3go adopted mode A), which declared the mirror
verified. The verify was true but empty of meaning; this node records why, and what
replaces it.

**Cause.** `import` stamps every node file with a `flywheel:` block that carries the
*archive's* `node_id` and `content_sha256` (`tools/hypergraph.py:1109`). `push_plan`
(`tools/hypergraph.py:1396`) then reads:

```python
if not flywheel.get("node_id"):                       # -> create
elif flywheel.get("content_sha256") != node.sha256:   # -> update
# otherwise: omitted from the plan entirely
```

An imported node has a `node_id` and a matching hash, so push omits it. The plan is
correct on its own terms — the node *is* on Flywheel. It is on a **different graph,
owned by someone else**. One field is doing three jobs at once:

1. provenance — where the node came from; belongs to the archive,
2. push target — which mirror node to update; belongs to the mirror,
3. change-detection baseline — belongs to the mirror.

**Why it stayed unseen.** a3go's `push --verify` was run against a **4-anchor union
export** — the 2 mirror roots *plus* the 2 archive roots. Splicing the archive into the
export makes the 105 orphaned ids resolve, so verify exits 0. Verify has never checked
the mirror on its own merits.

**Consequences.** A reader of a3go's mirror sees three record nodes and no history.
Nothing on the mirror points at the archive except prose inside the epoch marker body.
The archive is not ours — a3go's marker says so: *"the graph is public but not writable
by this account."* Git still holds the record, so no memory is lost, but the mirror
story breaks if that account removes the archive.

## Method

Design settled before implementation, in five parts:

1. **Split the identity.** A new `origin:` frontmatter block carries archive provenance
   (`backend`, `node_id`, `slug`, `revision`, `exported_at`) and is never read by push
   or verify. `flywheel:` keeps its single job — the mirror's identity, written only by
   `push --record-result`. `FM_ORDER` gains `origin` immediately before `flywheel`.
   No logic change in `push_plan` or `verify_mirror`: with `flywheel:` absent an
   imported node is planned as a `create`, parents-first, like any authored node.
   `check` reads neither block, so I1-I8 are untouched.

2. **`import --fork`.** Forking is opt-in. Plain `import` keeps today's behaviour
   because it has a second, still-valid use: re-homing a graph *you own* to the local
   backend while continuing to mirror to that same graph
   (`backend/local-adapter.md`, "Bootstrapping from Flywheel"). This very repo did
   that; dropping `flywheel:` there would duplicate the whole graph on the next push.
   `hypergraph-adopt` mode A always passes `--fork`.

3. **Lineage at the mirror root.** `hypergraph push --lineage` renders a body from a
   config `archive:` block — the same pattern as `--legend`. It names each archive
   root (slug, node_id, title), says the archive is frozen and never written to, gives
   the imported node count, and states plainly that artifacts stayed behind. The adopt
   skill uses it as the **body of the mirror record root**: the first thing a mirror
   reader sees. Reconcile refreshes it when `archive:` changes.

4. **Verify against the mirror alone.** Adopt and reconcile export **only** the roots
   in `mirror_roots:`. No archive anchors. With the full history pushed this passes on
   its own merits and becomes a real check instead of a tautology.

5. **Scale guard.** 108 creates is 108 MCP calls. `push --plan` warns on stderr above
   200 creates and names epoch-split as the alternative. A warning, not a violation —
   the adapter already handles 429 backoff.

Naming rule that falls out of it: **the mirror projects the repo, never the archive.**
The mirror root title convention drops the parenthetical (`a3go — record`, not
`a3go — record (hypergraph mirror)`); the mirror fact belongs in the body, which now
says it properly.

Out of scope and accepted: artifacts do not come along (the local backend has no
artifact operation) — stated explicitly at the mirror root; slug translation on push
stays deferred; the archive is never written to.

Migration needs no new command. `import` is idempotent, and both a3go archive anchors
(`purple-fog-6345`, `proud-king-2753`) were verified reachable today, so
`import --fork --force` over a fresh archive export rewrites the 108 legacy files.
Post-epoch nodes are absent from the archive export, so `--force` cannot touch them.
tbinn (mode B) has no `origin:` and already mirrors in full, so it needs no migration.

Design document: `SPEC-fork-import.md` (session scratchpad), reproduced above.

## Result

No code yet — this node is the decision. Planned milestones: M1 tooling + tests,
M2 docs + skills, M3 the live a3go migration (108 creates under our own roots, epoch
marker re-parented, lineage at the root, verify against mirror roots alone), M4
reconcile.

The highest-consequence risk is identified and mitigated in the plan: a 108-node push
that dies midway is only safely resumable if `--record-result` was applied for the
batches that already succeeded. Otherwise those nodes get created twice, and duplicates
on Flywheel cannot be cleanly merged. The adopt skill therefore gains an explicit
instruction to record push results **incrementally**, in batches of about 20, not once
at the end.

Two smaller risks stay open: re-parenting the epoch marker uses
`flywheel_add_node_parent` / `flywheel_remove_node_parent`, which are not in the
adapter's operation mapping and must be proven on one node first; and the slug legend
grows to about 118 rows.

Expected end state on a3go, measured over the two mirror roots **alone**: about 111
record nodes, 9 state nodes, 1 legend — against 3 record nodes today.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: b57334380aec1dba5cee9278253b557b252fec0d

## State Impact

- target: morning-crane-7863 — new milestone thrust opened: fork-import (origin/flywheel identity split, import --fork, push --lineage, mirror-only verify); adopted projects re-publish their whole imported history to a mirror they own
- target: blue-sun-8921 — negative knowledge: a mode-A mirror can verify clean while holding almost none of the graph, because the archive roots were spliced into the verify export and made the imported nodes' archive-owned ids resolve; scope: mode-A adoption, confidence: high
