---
node_id: b8c23938-e59c-524a-95d0-2c4228655d2c
slug: late-sage-5549
title: The state graph gets depth, a size budget, and an honest frontier
created_at: '2026-08-14T13:19:42+00:00'
parents:
- shady-bay-7654
summary: ''
flywheel:
  node_id: a0bc6040-7030-5f08-9b0d-6f7cd38fb8fe
  slug: icy-poetry-2348
  revision: 0
  pushed_at: '2026-08-14T13:20:34+00:00'
  content_sha256: fa6e502ce22fa387f487bbd3e54b3a0c99a5c2728a0aa729c4a779ff72efd52e
  parents_sha256: 35d4aced6341183bcafab135eb5c061a88a5627215f4d9b3175e40731f970d81
  parents:
  - f6c9cf38-4e65-519f-8a68-cdb66a9f0385
---
## What

The Operator described this project from memory, then read its state graph, and the
two did not match. Comparing them is the whole method here — it surfaced one defect in
the graph and one in the CLI, and it sets a reorganization of this repo's own state
graph into the shape the project is actually understood in.

The Operator's model: distribution, with PyPI and GitHub under it; a graph-structure
node with record and state children; protocol mechanics; skills; visualization with
children; Flywheel; autonomous operation. Most of that is in the state graph already —
flat, sometimes mis-named, and missing the two things the project's own tagline claims.

## Why

**Defect 1 — the state graph outgrew its own convention.** SPEC.md:209 says "the whole
state graph should be readable in one sitting". Measured today: **174 KB of node bodies
across 15 nodes** (208 KB of files including frontmatter). `morning-crane-7863` is 51
bullets / 18.8 KB on its own; `protocol-benchmark-4417` 50 / 17.6 KB;
`wandering-sun-8831` 48 / 15.9 KB; `empty-forest-6305` 45 / 19.4 KB. **Nothing detects
this.** Same failure class as the dropped tags [rec: fresh-spire-9002]: an unmeasured
category is invisible to every check by construction.

**Defect 2 — a state node could not be re-parented, and the mirror never found out.**
Discovered by planning this reorganization:

- `hypergraph update` took `--body/--title/--summary` only — no `--parent`.
- `push_plan` emitted an `update` op **only when `content_sha256` changed**, and that
  op carries no parents. A pure re-parent produced **no mirror op at all**.
- `parents` sat in `VERIFY_STRICT_FIELDS`, not `VERIFY_FIELDS`, so default
  `push --verify` could not see topology drift.

Net: nesting a node forked local topology from mirror topology, silently, forever. The
host was never the blocker — `backend/flywheel.md` already specified
`nodes:add-parent` / `nodes:remove-parent`, the add-before-remove ordering and the four
optimistic locks. The transport simply never implemented them.

**Why the reorganization goes first, as evidence.** The durable goal is teaching *every*
agent to build good state graphs. This round earns that claim on the protocol's own
graph rather than asserting it in SPEC prose. Generalizing it — a SPEC convention, a
`check` rule for state-graph size and shape, reconcile-skill guidance — is a **later
round**, fed by what this one measures.

## Method

Two things enter the record graph here: the CLI direction (Phase 1, implemented and
recorded in the child node that follows this one) and the target topology below, which
`## State Impact` declares in full for a single reconcile pass to fold.

Target topology, `[reparent]` marking an existing node that has to move:

```
cool-king-8586  hypergraph-protocol — state
├── Graph structure          young-wave-9364   (retitle from "Protocol spec")
│   ├── Record graph         NEW
│   └── State graph          NEW                                  [open]
├── Protocol mechanics       wandering-sun-8831 (retitle from "Checker tooling")
│   ├── Storage & node format blue-sun-8921    [reparent] (absorbs storage half of empty-forest-6305)
│   └── Retroactive repair   retroactive-repair-5104  [reparent]
├── Skills                   dry-wildflower-2260
├── Distribution             NEW
│   ├── PyPI releases        NEW  (shipped half of weathered-union-7494)
│   ├── GitHub repository    NEW  (lawful-birch-4414, placid-ridge-4035, long-peak-1620)
│   └── Announcement         weathered-union-7494 (narrowed)      [open]
├── Adoption                 morning-crane-7863
│   └── Upgrade path         fond-sail-3288    [reparent]
├── Dogfooding               bold-field-1268   (splits in two)
│   ├── Self-host            NEW  (from bold-field-1268)
│   └── Field                bitter-sound-9744 [reparent]
├── Visualization            polished-pond-2718
│   ├── Viz machinery        NEW  (bundler, single-file HTML, live mode)
│   └── Views                NEW  (the five job-named views)
├── Flywheel mirror          empty-forest-6305 (retitle; narrowed to the mirror)
├── Collaboration            gilded-vale-8087
├── Autonomous operation     NEW                                  [open]
│   └── Harness hygiene      fair-field-3265   [reparent]
└── Protocol benchmark       protocol-benchmark-4417              [open]
```

Why each change:

- **Graph structure / Record graph / State graph** — the Operator's model, and the one
  place "what makes a good state graph" can be a falsifiable claim. `State graph` is
  born **`open`**: it is the live hypothesis (SPEC.md:36) and this repo just proved it
  is unsolved by growing to 174 KB.
- **Distribution split** — `weathered-union-7494` is `open` while five releases shipped
  (0.0.2 → 0.0.8, all verified from the public index). The releases are *facts*; only
  the announcement is a gap. Splitting makes the frontier honest instead of a working
  capability flying an `open` flag.
- **Dogfooding split** — "Dogfooding" and "Field dogfooding" read as parent/child but
  sit as peers; `bold-field-1268` itself records that Field was spawned out of it. Two
  real evidence bases (this repo; a3go / tbinn / neural-whoop / hypergraph-labs).
- **Autonomous operation [open]** — SPEC.md:3, README.md:3 and AGENTS.md:3 all open
  with "a substrate for autonomous research and engineering", and **no state node
  claims anything about it**. There is also no auto-run skill. An empty frontier on a
  known ambition is a defect (SPEC: Forward work). `fair-field-3265` becomes its child:
  running agent fleets is operational hygiene *for* autonomy, not the thing itself.
- **Flywheel mirror** — `empty-forest-6305` covers both the local storage story and the
  mirror. Storage moves under Protocol mechanics; the node keeps the mirror and gets
  the name the Operator uses for it.

**Size budget: ≤ 60 KB of state-node bodies, no single node over 6 KB** (from 174 KB /
18.8 KB max). The honest tradeoff is that node count rises 15 → ~22, so compaction is
not optional. Every node touched gets merged redundant claims, dropped superseded
detail (the record graph keeps it — SPEC.md:209), and tightened negative knowledge.
Negative knowledge is **preserved verbatim**; it is the least recoverable content in
the graph. Provenance is redistributed, never dropped — every record slug cited today
must still be cited by whichever node inherits its claim (SPEC I4).

## Result

A direction, not an outcome: no state node has moved yet beyond the single-node canary
Phase 1 needed (`retroactive-repair-5104` under `wandering-sun-8831`, proved against
the live mirror). The impacts below are what one reconcile pass folds.

Deliberately **out of scope this round**, so the next one has something falsifiable to
carry: any new `check` rule, any SPEC convention edit beyond what the reorganization
requires, and a "concept/theory" state node — the *why* stays in SPEC.md's preamble and
decision record `spring-pine-7256`, since a theory node would never be falsified and
would rot into a doc. Its state-shaped form already exists as `protocol-benchmark-4417`
[open].

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 437fcee23bf6395e0ac3615644febb32b3e2821d

## State Impact

- target: young-wave-9364 — retitle to "Graph structure"; narrow to the two-graph structure and gain two children; compact
- target: NEW record-graph — child of Graph structure: what the append-only half is and what makes one good
- target: NEW state-graph — child of Graph structure, born [open]: the live hypothesis, unsolved — this repo grew to 174 KB with nothing detecting it
- target: wandering-sun-8831 — retitle to "Protocol mechanics"; gain two children; compact
- target: blue-sun-8921 — reparent under Protocol mechanics; retitle to "Storage & node format"; absorb the storage half of empty-forest-6305
- target: retroactive-repair-5104 — reparented under Protocol mechanics (done as the Phase 1 live canary)
- target: dry-wildflower-2260 — compact to the size budget; keep the five skills and their negative knowledge
- target: NEW distribution — child of the root: how the protocol reaches anyone, with PyPI, GitHub and the announcement under it
- target: NEW pypi-releases — child of Distribution: the shipped half of weathered-union-7494, five releases verified from the public index
- target: NEW github-repository — child of Distribution: the public repo, CI and PR workflow
- target: weathered-union-7494 — retitle to "Announcement"; reparent under Distribution; narrow to the unshipped half; stays [open]
- target: morning-crane-7863 — compact from 51 bullets to the size budget; gain Upgrade path as a child
- target: fond-sail-3288 — reparent under Adoption
- target: bold-field-1268 — split: keeps Dogfooding as the parent of two evidence bases; gains Self-host and Field as children
- target: NEW self-host — child of Dogfooding: this repo running under its own protocol
- target: bitter-sound-9744 — reparent under Dogfooding; retitle to "Field"
- target: polished-pond-2718 — split into machinery and views; keep Visualization as their parent
- target: NEW viz-machinery — child of Visualization: bundler, single-file HTML, live mode
- target: NEW views — child of Visualization: the five job-named views
- target: empty-forest-6305 — retitle to "Flywheel mirror"; narrow to the mirror once storage moves to blue-sun-8921
- target: NEW autonomous-operation — child of the root, born [open]: the tagline claim no state node makes, with no auto-run skill behind it
- target: fair-field-3265 — reparent under Autonomous operation as its operational-hygiene child
- target: gilded-vale-8087 — compact; stays a child of the root
- target: protocol-benchmark-4417 — compact from 50 bullets; stays [open] and stays the state-shaped form of the theory
- target: cool-king-8586 — the architecture becomes a nested tree of depth 2; frontier grows from two honest gaps to four
