# Hypergraph Protocol — v0.0.1

Hypergraph is a protocol for maintaining **two graphs per research project** on top of a
graph store (v0.0.1 backend: [Flywheel](backend/flywheel-adapter.md)):

- **Record graph** — the append-only historical log of everything that happened:
  decisions, experiments, evidence, dead ends. Topology is causal/chronological.
- **State graph** — a small, single-writer, distilled projection of what is true *now*:
  the project's architecture, what currently works, what's broken or open (the
  **frontier**), and accumulated negative knowledge. Topology mirrors the project's
  architecture (components/capabilities), not history.

Every state node cites the record nodes it derives from — a many-to-one provenance
mapping across the two graphs. That cross-graph citation structure is the "hypergraph."

The point: a fresh agent landing on a mature project should orient to the frontier in a
handful of tool calls instead of traversing thousands of record nodes.

## Vocabulary

- **Record node** — a node in the record graph. Immutable once committed (append-only
  discipline; the backend may technically allow edits, the protocol forbids them except
  for typo-level fixes that don't change meaning).
- **State node** — a node in the state graph. Mutable, rewritten in place by
  reconciliation. Represents one component/capability/concern of the project.
- **Slug** — the backend's immutable human-readable node handle. For Flywheel:
  `adjective-noun-####` (e.g. `quiet-snow-3839`). Slugs are how the two graphs point at
  each other; cross-graph pointers are **structured markdown, never graph edges** —
  graph edges between the two DAGs would topologically merge them.
- **Frontier** — the set of state nodes with status `open`, `broken`, or `blocked`.
  This is what a fresh agent should read first.
- **High-water mark (HWM)** — the most recent record node whose declared state impact
  has been folded into the state graph.
- **Reconcile** — the single-writer pass that folds record-node impact declarations
  into the state graph and advances the HWM.

## Invariants

Numbered invariants are the protocol. I2, I4, I5, I6, and I7 are mechanically enforced
by `tools/hypergraph.py check`; I1, I3, and I8 are procedural (enforced by the skills),
with the checker reporting proxies where it can.

### I1 — Record-first

No knowledge exists only in the state graph. New information (results, decisions,
failures, insights) lands in the record graph first; the state graph is a *projection*,
never the primary home of anything. Every state edit is triggered by, and cites, at
least one record node.

*Checker proxy:* claims in a state node's `## Current` section with no inline
`[rec: <slug>]` citation are reported as warnings.

### I2 — Impact declaration

Every record node except the record root carries a `## State Impact` section, parseable
as one of:

1. One or more impact lines:
   - `- target: <state-slug> — <delta>` — the delta to fold into an existing state node.
   - `- target: NEW <kebab-name> — <delta>` — reconcile should create a new state node.
2. Exactly `none: <reason>` — an explicit declaration that this node changes nothing
   about current state, with a non-empty reason.

`<state-slug>` must resolve to an existing state node. `<delta>` is a non-empty
human-readable description of what changes (status flip, new claim, new negative
knowledge, supersession). Writing the impact is the *recording* agent's job — it is a
declaration, not a state write (see I3).

### I3 — Single-writer state

Only the reconcile pass writes state nodes. Recording agents — including many running
in parallel — only ever append record nodes with impact declarations. This avoids
stage-lease contention on hot state nodes and prevents weakest-agent drift in the
distilled projection. Procedural; the reconcile skill is the only skill that acquires
leases on state nodes.

### I4 — Provenance

Every state node except the state root has a `## Provenance` section listing the record
slugs it derives from, one per line:

- `- <record-slug> — <why this record node informs this state node>`

Every slug in `## Provenance` must resolve to a record-graph node. Claims in
`## Current` cite record slugs inline with `[rec: <slug>]`; every inline citation must
also resolve. Provenance is many-to-one: a state node typically cites many record nodes.

### I5 — High-water mark

The state root's content carries a `## Reconciliation` section:

```
## Reconciliation
- high_water_mark: <record-slug or none>
- reconciled_at: <ISO-8601 timestamp>
```

Because the record graph is append-only, "everything through node N is folded in" is a
complete description of reconciliation progress, and reconcile runs idempotently from
it. Record nodes created after the HWM node are *unreconciled* — enumerable by the
checker, which reports their count and per-state-node staleness. Unreconciled nodes are
normal between reconcile runs; a missing/unresolvable HWM is a violation.

### I6 — Status vocabulary

The first non-blank line of every state node except the state root is:

```
Status: working | open | broken | blocked | superseded
```

- `working` — implemented and believed correct.
- `open` — planned/known-unknown; work not yet done.
- `broken` — was working or attempted, currently fails.
- `blocked` — cannot proceed until something outside this node changes.
- `superseded` — replaced by another state node (name it in `## Current`).

**Frontier = open ∪ broken ∪ blocked.**

### I7 — Negative knowledge

Entries in a state node's `## Negative knowledge` section are scoped,
confidence-rated, and evidence-cited:

```
- [scope: <where this applies> | confidence: low|medium|high | evidence: <slug>, <slug>] <statement>
```

An optional `| decision: <record-slug>` field cites the decision record that authorized
a generalization. If `scope` begins with `general`, the `decision:` field is
**required**: generalizing "2 failures" into "this approach is dead everywhere" is
itself a decision and needs its own decision record node. Evidence and decision slugs
must resolve to record nodes.

### I8 — Rebuildability (audit definition)

A re-derivation of any state node from its cited record nodes must be *semantically
equivalent* to the committed state node — same status, same claims, same negative
knowledge, possibly different wording. This is audit-grade provenance, not byte
determinism.

*Spot-check procedure:* pick a state node; fetch only the record nodes listed in its
`## Provenance`; without looking at the state node body, write down status + claims +
negative knowledge you'd derive; compare. A mismatch means either provenance is
incomplete (fix: add the missing record slugs, or record the missing knowledge first —
I1) or reconcile hallucinated (fix: rewrite the state node from its citations).

## Conventions (skill-enforced)

- **Record topology is causal.** Choose a record node's parent by causal relation —
  "this work followed from that result" — not recency, and never default to root-only
  branching (per the backend's own topology guidance). Independent workstreams may
  branch from the root.
- **State topology mirrors architecture.** State children of the state root are the
  project's components/capabilities. Depth stays shallow (2–3 levels). Reorganizing
  state topology is a reconcile-only operation and needs a decision record node.
- **Record nodes carry repo context.** When code is involved, record the commit SHA in
  `## Repo` and in the backend's repo-context fields (`repo_url`, `branch_name`,
  `head_commit_sha`).
- **Evidence lives on record nodes.** Artifacts (logs, plots, datasets) attach to
  record nodes, never state nodes. State nodes point at them via provenance slugs.
- **State stays small.** The whole state graph should be readable in one sitting.
  Reconcile compacts: merge redundant claims, drop superseded detail (the record graph
  keeps the history), keep negative knowledge tight.

## Node templates

Exact headings are load-bearing — the checker parses them. See
[templates/record-node.md](templates/record-node.md) and
[templates/state-node.md](templates/state-node.md).

- Record node content: `## What / ## Why / ## Method / ## Result / ## Repo / ## State Impact`
- State node content: `Status:` line, then `## Current / ## Negative knowledge / ## Provenance`
- State root content: project overview + `## Reconciliation`

## Per-project files

Created by the `hypergraph-init` skill in the target repo:

- `.hypergraph/config.yml` — project name, record root and state root (node_id + slug).
  See [templates/config.example.yml](templates/config.example.yml).
- `.hypergraph/cache/{record,state}.json` — graph exports consumed by the checker and
  renderer (gitignored; regenerated by reconcile).
- `STATE.md` — generated snapshot of the state graph (regenerated by reconcile, never
  hand-edited). Frontier at the top, architecture tree below.

## Tooling

`tools/hypergraph.py` (single-file uv script) consumes JSON exports — no auth, no
network, deterministic, CI-ready:

```
uv run tools/hypergraph.py check  --record .hypergraph/cache/record.json --state .hypergraph/cache/state.json
uv run tools/hypergraph.py render --state .hypergraph/cache/state.json --config .hypergraph/config.yml -o STATE.md
```

`check` exits nonzero on any I2/I4/I5/I6/I7 violation.

## Backend

The protocol is written against ~10 abstract operations
([backend/INTERFACE.md](backend/INTERFACE.md)) so the graph store is swappable.
v0.0.1 ships one adapter: [backend/flywheel-adapter.md](backend/flywheel-adapter.md).

## Future work (out of scope for v0.0.1)

- Hooks-based `unreconciled` auto-tagging of record nodes past the HWM.
- `provenance.json` machine-readable artifact per state node.
- One-only `current-best` tags for competing approaches (Flywheel supports natively).
- State graph visualizer.
- Git-native open backend (second adapter; the interface is designed for it).
- pip-installable package.
