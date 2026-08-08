# Hypergraph

A protocol for keeping research projects legible to fresh agents. Hypergraph maintains
**two graphs per project** on top of a graph store — [markdown files in your
repo](backend/local-adapter.md), or a hosted one like [Flywheel](backend/flywheel-adapter.md):

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
append-only high-water mark. Nobody edits state inline. Forward work follows the same
rule: new directions (including Operator directives) enter as decision record nodes
whose impacts open `Status: open` state nodes — the frontier carries intent as claims
about gaps, never as task lists.

## Two backends

The protocol is written against a [thin abstract backend
interface](backend/INTERFACE.md) — ~10 operations — and two adapters implement it. Pick
one at init time; `backend:` in `.hypergraph/config.yml` is what every skill dispatches
on.

| | **`local`** ([adapter](backend/local-adapter.md)) | **`flywheel`** ([adapter](backend/flywheel-adapter.md)) |
|---|---|---|
| Source of truth | committed `.md` files in your repo | hosted graph store over MCP |
| Requires | nothing (offline, no account) | Flywheel MCP |
| Writes | `hypergraph new` / `update` | `flywheel_commit_new_node` / lease→commit |
| Op 7 concurrency | body-hash CAS (`--expect`) + git | `base_committed_revision` (409) |
| Good for | solo/offline work, the graph travelling with the repo, CI | hosting, cloud agents, a graph shared across repos |

Flywheel is the **recommended** path when you want your graph reachable by agents that
aren't sitting in your working tree. The local backend is fully independent of it, and
the two compose: `backend: local` + `mirror: flywheel` keeps the files canonical and
Flywheel a regenerable projection, refreshed at the end of each reconcile.

## What ships

- **[SPEC.md](SPEC.md)** — the protocol: invariants I1–I8 + conventions.
- **[skills/](skills/)** — five Claude skills: `hypergraph-init`, `hypergraph-adopt`
  (bring a project with a past under the protocol: legacy-graph import or authored
  prehistory, adoption epoch, AGENTS.md onboarding), `hypergraph-record`,
  `hypergraph-reconcile`, `hypergraph-orient`.
- **[tools/hypergraph.py](tools/hypergraph.py)** — single-file uv script: `check`
  validates the mechanical invariants over JSON graph exports (CI-ready, nonzero exit
  on violations); `render` generates `STATE.md` (frontier first, architecture tree
  below); `viz` emits a self-contained interactive HTML visualization — record view,
  state view, and the combined hypergraph view with cross-graph provenance/impact
  links (zero JS dependencies, no network; opens straight from `file://`); and
  `export`/`import`/`new`/`update`/`push` implement the local backend.
- **[templates/](templates/)** — the exact markdown shapes the checker parses.

## Quickstart

```bash
./install.sh                       # symlink the skills into ~/.claude/skills

# in a Claude session inside your project repo:
#   run hypergraph-init            → roots + state skeleton + .hypergraph/config.yml + STATE.md
#   ... do work; run hypergraph-record after each unit of work
#   run hypergraph-reconcile       → fold impacts into state, regenerate STATE.md
#   (fresh session) hypergraph-orient → frontier brief in ≤ ~6 tool calls
```

The local backend, standalone — no MCP anywhere in this loop:

```bash
hypergraph new record --title "Fixed the streaming parser" --body body.md \
    --parent <causal-slug> --impact "<state-slug> — status broken → working" --repo-auto
hypergraph export --config .hypergraph/config.yml     # node files → cache JSON
uv run tools/hypergraph.py check --record .hypergraph/cache/record.json \
    --state .hypergraph/cache/state.json --config .hypergraph/config.yml
git add .hypergraph/graph                             # the memory travels with the repo
```

Already on Flywheel — or adopting a repo with real history? Run the
`hypergraph-adopt` skill: it imports the legacy graph verbatim (`hypergraph import
--fork` preserves node_ids and slugs, so provenance and the high-water mark stay
valid), draws an adoption epoch so legacy nodes are exempt from template compliance,
and distills an honest state graph from what the project actually knows. The import
is a **fork**: the source graph stays frozen as the archive, and the project
re-publishes its *whole* imported history to a mirror it owns, with the original
topology and a lineage pointer at the mirror root naming where it came from.

Checker/renderer/visualizer, standalone:

```bash
uv run tools/hypergraph.py check  --record .hypergraph/cache/record.json --state .hypergraph/cache/state.json
uv run tools/hypergraph.py render --state .hypergraph/cache/state.json --config .hypergraph/config.yml -o STATE.md
uv run tools/hypergraph.py viz    --record .hypergraph/cache/record.json --state .hypergraph/cache/state.json \
                                  --config .hypergraph/config.yml -o .hypergraph/viz.html
open .hypergraph/viz.html          # interactive: pan/zoom, click nodes, search; SVG/PDF export
uv run pytest tests/               # checker + viz test suite over committed fixtures
```

The viz page is one unified view driven by a **Display** section in the sidebar:
graph visibility (record / state / both), node style (cards / circles), layout
(layered / force — independent of node style), and per-species edge toggles
(parent edges, impact links, provenance links, hyperedge blobs — each state
node's contributing record set drawn as a convex-hull blob; deterministic layout,
no randomness). Preset chips — **Record**, **State**, **Columns** (record log and
state projection side by side with cross-graph links), **Force** (force-directed
circles with blobs) — reproduce the classic arrangements, and any custom mix in
between is fair game. The sidebar is resizable (drag the divider) and collapsible
(click it); exports live in the header's download menu. Deep links still work:
`viz.html#record`, `#state`, `#combo`, `#hyper`, or `#<any-slug>` to jump straight
to a node.

## Repo map

```
SPEC.md                     the protocol (invariants + conventions)
backend/INTERFACE.md        ~10 abstract backend operations
backend/local-adapter.md    op → node files + hypergraph CLI (git-native)
backend/flywheel-adapter.md op → Flywheel MCP call recipes
skills/hypergraph-*/        the five skills (install.sh symlinks these)
templates/                  record-node / state-node / config shapes
tools/hypergraph.py         checker + renderer + visualizer + local backend (uv script)
tools/fixtures/             test fixtures (clean, per-invariant violations, local-graph)
tests/                      pytest suites (checker + viz + local backend)
```

This repo dogfoods itself: see [.hypergraph/config.yml](.hypergraph/config.yml) and
[STATE.md](STATE.md).
