# A worked example, on real nodes

The smallest complete Hypergraph project lives in this repo at
[`tools/fixtures/local-graph/`](../tools/fixtures/local-graph/) — three record
nodes and two state nodes, pinned by CI on every test run, so unlike a prose
example it cannot rot. This page walks it: what a node is on disk, how the
graphs export and check, and how the record→reconcile loop moved a status.

The story in it: a project prototyped CSV ingest, hit an out-of-memory wall,
fixed it with a streaming parser, and its state graph remembers both the
working result and the dead end.

## Anatomy of a record node

`graph/record/brave-otter-1002.md` — one unit of work, one file:

```markdown
---
node_id: 9810511f-edb5-563f-a7c6-320bc6e11516   # uuid5 of the slug
slug: brave-otter-1002                           # permanent handle
title: Prototyped CSV ingest; hit an OOM wall
created_at: '2026-08-02T01:00:00+00:00'
parents:
- wise-anchor-1001                               # causal parent, by slug
summary: ''
---
## What

Built the first ingest prototype and measured it on a 2.3GB CSV.

## Why

Root of an independent workstream: nothing ingests data yet.

## Method

`python ingest.py --input big.csv`, pandas chunked reader, chunksize=100k.

## Result

OOM at 6.1GB RSS on a 4GB box. The chunked reader still materializes the whole
frame at concat time; this approach is dead without a memory budget.

## State Impact

- target: NEW ingest — new component covering CSV ingest, status open
```

Three things to notice. The frontmatter is identity and topology; the body is
the claim. **A dead end is recorded exactly like a success** — this node's
`## Result` is a failure, and it becomes the most valuable line in the state
graph below. And the `## State Impact` section (invariant I2) declares what the
distilled state should absorb, without writing it: `NEW ingest` asks the
reconcile pass to create a component node.

Its child, `calm-fern-1003`, records the fix and declares the delta against the
state node that by then exists:

```markdown
## State Impact

- target: quiet-summit-2002 — status open → working; OOM becomes negative knowledge
```

## Anatomy of a state node

`graph/state/quiet-summit-2002.md` — what is true *now*, every claim citing the
record node it rests on:

```markdown
Status: working

## Current

- Streaming csv parser ingests multi-GB files (2.3GB in 84s, 210MB peak RSS) [rec: calm-fern-1003].

## Negative knowledge

- [scope: ingest of files >2GB | confidence: medium | evidence: brave-otter-1002] pandas chunked reader OOMs at concat time; do not revisit without a memory budget.

## Provenance

- brave-otter-1002 — created this component and documented the OOM failure
- calm-fern-1003 — streaming parser fix that made it work
```

The `Status:` line is invariant I6 (working/open/broken/blocked/superseded);
`[rec: …]` citations are I1's currency; `## Provenance` is I4; the
negative-knowledge entry — scope, confidence, evidence — is I7, and it is the
line that stops the next agent from wasting a day rediscovering the OOM. The
state root (`bright-harbor-2001`) additionally carries `## Reconciliation` with
the I5 high-water mark:

```markdown
## Reconciliation

- high_water_mark: calm-fern-1003
- reconciled_at: 2026-08-02T03:00:00+00:00
```

## Export, then check

```bash
$ hypergraph export --graph-dir graph --out-dir cache
wrote cache/record.json (3 record node(s))
wrote cache/state.json (2 state node(s))

$ hypergraph check --record cache/record.json --state cache/state.json
info      I5 [bright-harbor-2001] 0 unreconciled record node(s) past high-water mark

check: 0 violation(s), 0 warning(s)          # exit 0
```

The exports are the contract — the checker, the renderer, and any external
visualizer read the same two JSON files, never the markdown directly.

## What a violation looks like

The suite keeps one broken fixture per mechanically-enforced invariant under
[`tools/fixtures/violations/`](../tools/fixtures/violations/). Deleting the
`## State Impact` section from a record node (the `i2-missing-impact` fixture)
gets:

```bash
$ hypergraph check --record record.json --state state.json
VIOLATION I2 [calm-heron-0003] missing `## State Impact` section

check: 1 violation(s), 0 warning(s)          # exit 1
```

Exit 1 on findings, exit 2 on a usage/environment error — the full table is in
[cli.md](cli.md).

## Render

`hypergraph render --state cache/state.json -o STATE.md` writes the generated
snapshot: the frontier first (broken → blocked → open — what needs attention),
then the architecture tree. `hypergraph sync` does export → render → check →
publish in one step and is the gate every skill ends on.

## The loop this fixture froze

What produced these five files is the protocol's whole rhythm:

1. Work happened; `brave-otter-1002` recorded it — including the failure — and
   declared `NEW ingest` (the record skill; any branch, any contributor).
2. A reconcile pass created `quiet-summit-2002` as `open`, folding the OOM in.
3. The fix landed as `calm-fern-1003`, declaring the status flip.
4. The next reconcile flipped the status to `working`, moved the OOM into
   negative knowledge with its evidence slug, appended provenance, and advanced
   the high-water mark to `calm-fern-1003` — which is why `check` reports
   0 unreconciled above.

A fresh agent landing here reads `STATE.md`, sees ingest `working` with one
warning not to revisit pandas, and follows `[rec: calm-fern-1003]` into the
record graph only if the task demands the history.
