# Hypergraph

A protocol for keeping research projects legible to fresh agents. Hypergraph maintains
**two graphs per project** on top of a graph store (v0.0.1: [Flywheel](backend/flywheel-adapter.md)):

- **Record graph** — the append-only log of everything that happened: decisions,
  experiments, evidence, dead ends. Optimized for audit, not orientation.
- **State graph** — a small, single-writer, distilled projection of what is true
  *now*: architecture, what works, what's broken or open (the **frontier**), and
  accumulated negative knowledge. Every state node cites the record nodes it derives
  from — that many-to-one cross-graph provenance is the "hypergraph".

The problem it solves: on a mature project, cold-start orientation over an append-only
DAG means traversing thousands of nodes. With Hypergraph, a fresh agent reads the
frontier in ≤ ~6 tool calls and follows provenance slugs into the record graph only
where the task demands history.

How it stays coherent with many parallel agents: knowledge lands **record-first** —
every record node declares its `## State Impact` (or `none: <reason>`), and a separate
single-writer **reconcile** pass folds declared impacts into the state graph behind an
append-only high-water mark. Nobody edits state inline.

## v0.0.1 = protocol + skills + checker

Deliberately not a package. Flywheel (MCP) is the load-bearing graph store; the
protocol is written against a [thin abstract backend interface](backend/INTERFACE.md)
so an open, git-native backend can be a drop-in second adapter later.

- **[SPEC.md](SPEC.md)** — the protocol: invariants I1–I8 + conventions.
- **[skills/](skills/)** — four Claude skills: `hypergraph-init`, `hypergraph-record`,
  `hypergraph-reconcile`, `hypergraph-orient`.
- **[tools/hypergraph.py](tools/hypergraph.py)** — single-file uv script: `check`
  validates the mechanical invariants over JSON graph exports (CI-ready, nonzero exit
  on violations); `render` generates `STATE.md` (frontier first, architecture tree
  below).
- **[templates/](templates/)** — the exact markdown shapes the checker parses.

## Quickstart

```bash
./install.sh                       # symlink the skills into ~/.claude/skills

# in a Claude session inside your project repo (Flywheel MCP connected):
#   run hypergraph-init            → roots + state skeleton + .hypergraph/config.yml + STATE.md
#   ... do work; run hypergraph-record after each unit of work
#   run hypergraph-reconcile       → fold impacts into state, regenerate STATE.md
#   (fresh session) hypergraph-orient → frontier brief in ≤ ~6 tool calls
```

Checker/renderer, standalone:

```bash
uv run tools/hypergraph.py check  --record .hypergraph/cache/record.json --state .hypergraph/cache/state.json
uv run tools/hypergraph.py render --state .hypergraph/cache/state.json --config .hypergraph/config.yml -o STATE.md
uv run pytest tests/               # checker test suite over committed fixtures
```

## Repo map

```
SPEC.md                     the protocol (invariants + conventions)
backend/INTERFACE.md        ~10 abstract backend operations
backend/flywheel-adapter.md op → Flywheel MCP call recipes
skills/hypergraph-*/        the four skills (install.sh symlinks these)
templates/                  record-node / state-node / config shapes
tools/hypergraph.py         checker + STATE.md renderer (uv script)
tools/fixtures/             checker test fixtures (clean + per-invariant violations)
tests/test_checker.py       pytest suite
```

This repo dogfoods itself: see [.hypergraph/config.yml](.hypergraph/config.yml) and
[STATE.md](STATE.md).
