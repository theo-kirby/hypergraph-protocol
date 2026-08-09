# Hypergraph

A protocol for keeping research projects legible to fresh agents. Hypergraph maintains
**two graphs per project**, kept as [markdown files committed in your
repo](backend/local-adapter.md):

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

## Where the graphs live

In your repo. Each node is a committed markdown file under
`.hypergraph/graph/<record|state>/<slug>.md` — frontmatter carrying identity and parent
slugs, body carrying the content verbatim
([local-adapter.md](backend/local-adapter.md)). Nothing to sign in to, nothing to
install a server for: the graphs travel with the repo, work offline, merge through git,
and check in CI.

There is no backend to choose. The protocol is still *written* against a [thin abstract
interface](backend/INTERFACE.md) — ~10 operations — but that is a portability property,
not a setting: it is what a replacement store would have to satisfy, and why nothing in
the spec above the Storage section mentions files.

**Optionally**, `hypergraph push` mirrors your committed node files to a hosted
[Flywheel](https://flywheel.paradigma.dev) graph you own, so agents that aren't sitting
in your working tree can read them. The mirror is a one-way, regenerable projection —
your files stay canonical — and it is entirely a property of the CLI: the skills don't
know it exists, and a project without it never touches that path
([mirror.md](backend/mirror.md)).

## What ships

- **[SPEC.md](SPEC.md)** — the protocol: invariants I1–I8 + conventions.
- **[skills/](skills/)** — five Claude skills: `hypergraph-init`, `hypergraph-adopt`
  (bring a project with a past under the protocol: legacy-graph import or authored
  prehistory, adoption epoch, AGENTS.md onboarding), `hypergraph-record`,
  `hypergraph-reconcile`, `hypergraph-orient`.
- **[tools/hypergraph.py](tools/hypergraph.py)** — single-file uv script: `check`
  validates the mechanical invariants over JSON graph exports (CI-ready, nonzero exit
  on violations); `render` generates `STATE.md` (frontier first, architecture tree
  below); `viz` emits a self-contained interactive HTML visualization — four views
  (Timeline, Frontier, Provenance, Clusters), each with a layout that fits its data
  (zero JS dependencies, no network; opens straight from `file://`), or an
  excaligraph spec for hand-editable excalidraw figures; `export`/`import`/`new`/
  `update` are the storage layer, and `push`/`sync`/`mirror` the optional mirror.
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

The whole loop, in the repo — no account, no network:

```bash
hypergraph new record --title "Fixed the streaming parser" --body body.md \
    --parent <causal-slug> --impact "<state-slug> — status broken → working" --repo-auto
hypergraph export --config .hypergraph/config.yml     # node files → cache JSON
uv run tools/hypergraph.py check --record .hypergraph/cache/record.json \
    --state .hypergraph/cache/state.json --config .hypergraph/config.yml
git add .hypergraph/graph                             # the memory travels with the repo
```

Adopting a repo with real history — or an existing hosted graph? Run the
`hypergraph-adopt` skill: it imports the legacy graph verbatim (`hypergraph import
--fork` preserves node_ids and slugs, so provenance and the high-water mark stay
valid), draws an adoption epoch so legacy nodes are exempt from template compliance,
and distills an honest state graph from what the project actually knows. The import
is a **fork**: the source graph stays frozen as the archive, and the repo becomes the
continuing graph, owning its whole history with the original topology. Artifacts do
not travel — they stay on the archive, and the adopted project says so.

Checker/renderer/visualizer, standalone:

```bash
uv run tools/hypergraph.py check  --record .hypergraph/cache/record.json --state .hypergraph/cache/state.json
uv run tools/hypergraph.py render --state .hypergraph/cache/state.json --config .hypergraph/config.yml -o STATE.md
uv run tools/hypergraph.py viz    --record .hypergraph/cache/record.json --state .hypergraph/cache/state.json \
                                  --config .hypergraph/config.yml -o .hypergraph/viz.html
open .hypergraph/viz.html          # interactive: pan/zoom, click nodes, search; SVG/PDF export
uv run pytest tests/               # checker + viz test suite over committed fixtures
```

The page has four views, each named after the question it answers, and each with a
layout that fits the shape of its data:

- **Timeline** — the record graph as `git log --graph` lanes, time along x. A
  record graph is a timeline with a few concurrent threads, not a DAG to be
  ranked. Chips are compact; the x axis switches between even `rank` spacing and
  real dates with idle gaps compressed. A rule marks the high-water mark and the
  unreconciled tail behind it is tinted.
- **Frontier** — the state graph as a status board: `broken | blocked | open |
  working | superseded`, frontier first, newest work first inside a column. Empty
  columns collapse to a labelled rail rather than vanishing, because "nothing is
  broken" is an answer. A toggle switches to the architecture tree from `STATE.md`.
- **Provenance** — record log and state projection side by side. Cross-graph links
  default to **focus**: none are drawn until you select or hover a node, because
  177 links over 51 nodes is a hairball however it is drawn. **All** bundles them
  into one ribbon per claim through a shared spine.
- **Clusters** — each state node's contributing record set drawn as a blob, using
  a signed distance field (per-member outline, a corridor along a spanning tree,
  smooth merging, and non-members pushing the boundary away) rather than a convex
  hull, which would swallow whatever sat between three far-apart members.

Underneath, a **Display** section mixes the pieces freely: graph visibility,
node style, layout, cross-link mode and per-species edge toggles. Nothing fits
below 0.45 zoom — a view that does not fit scrolls instead of shrinking to
illegibility. The layout is deterministic: no randomness anywhere, so two renders
of the same graph give identical output. The sidebar is resizable (drag the
divider) and collapsible (click it); exports live in the header's download menu.
Deep links: `viz.html#timeline`, `#frontier`, `#provenance`, `#clusters`, or
`#<any-slug>` to jump to a node. The pre-rename hashes (`#record`, `#state`,
`#combo`, `#hyper`) still resolve.

### Excalidraw figures

For a figure you can hand-edit, `viz` also emits a graph spec for **excaligraph**
(MIT), which turns it into an Excalidraw scene. It is deliberately a two-step:
`hypergraph.py` never shells out, and node stays optional.

```bash
uv run tools/hypergraph.py viz --format excaligraph \
    --record .hypergraph/cache/record.json --state .hypergraph/cache/state.json \
    --config .hypergraph/config.yml -o graph.yaml
excaligraph build graph.yaml -o graph.excalidraw     # then open it in excalidraw.com
excaligraph preview graph.excalidraw -o graph.svg    # …or render it headlessly
```

### Live mode

`--live` writes `viz.html` *plus* a sibling `viz.data.json`, and the page polls
that file, redrawing and pulsing whatever appeared since the last poll — a status
board for a run in progress. It is the one output that is deliberately **not**
self-contained, which is why it is a flag and not the default:

```bash
uv run tools/hypergraph.py viz --live --record .hypergraph/cache/record.json \
    --state .hypergraph/cache/state.json --config .hypergraph/config.yml \
    -o .hypergraph/viz.html
python3 -m http.server -d .hypergraph      # browsers block fetch from file://
```

Re-run `export` and `viz --live` (from a watcher, a commit hook, or a loop) and
the open page catches up on its own. If the data file cannot be reached, the
indicator in the header says so and polling stops rather than failing silently.

Nodes are coloured by the same status palette the page uses, so a figure and the
page never disagree, and each one carries a `link:` back to its markdown source.
Each state node's impact set becomes a hyperedge blob. Cross-graph edges are off
by default (`--links none|provenance|impact|all`) for the same reason the page
defaults to focus — and because the impact relation *is* the blob membership, so
drawing it again as edges says nothing new.

## Repo map

```
SPEC.md                     the protocol (invariants + conventions)
backend/INTERFACE.md        ~10 abstract operations — the portability contract
backend/local-adapter.md    op → node files + hypergraph CLI (git-native; the one impl)
backend/mirror.md           optional one-way mirroring — CLI internals, not agent-facing
backend/flywheel-adapter.md the host's payload/lease contract, for the mirror code only
skills/hypergraph-*/        the five skills (.claude/skills/ symlinks these)
templates/                  record-node / state-node / config shapes
tools/hypergraph.py         checker + renderer + visualizer + storage + mirror (uv script)
tools/bundle_viz.py         dev tool: bundles tools/viz/* into the page constant
tools/viz/                  the viz page's sources (html + css + js parts)
tools/fixtures/             test fixtures (clean, violations, local-graph, self)
tests/                      pytest suites (checker + viz + local backend)
tests/browser/              playwright layout baselines (dev group; self-skipping)
```

This repo dogfoods itself: see [.hypergraph/config.yml](.hypergraph/config.yml) and
[STATE.md](STATE.md).
