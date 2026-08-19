# Hypergraph

**A substrate for autonomous research and engineering.**

The goal is agents that carry out real research and real engineering over months
without a human holding the thread — and the obstacle is not agent capability. It is
that agents are made to work in a substrate that does not support the shape of the
job. Chat logs are not memory. A codebase records what was kept, never what was tried
and rejected. A task list rots the moment reality moves. So every fresh context
re-derives what the last one already knew, repeats dead ends nobody wrote down, and
quietly contradicts decisions it never saw. That failure is structural, not a prompting
problem, and no amount of context window fixes it.

Hypergraph is an attempt at a substrate where those failures are not available.
Knowledge has somewhere to go, being wrong is a first-class outcome, and the thing an
arriving agent reads first is *what is true now* rather than everything that ever
happened. Its unit of work is not a commit or a ticket — it is a claim with its
evidence attached.

It maintains **two graphs per project**, kept as [markdown files committed in your
repo](backend/local-adapter.md):

- **Record graph** — the append-only log of everything that happened: decisions,
  experiments, evidence, dead ends. Optimized for audit, not orientation.
- **State graph** — a small, single-writer, distilled projection of what is true
  *now*: architecture, what works, what's broken or open (the **frontier**), and
  accumulated negative knowledge.

A project can keep further **named views** — extra derived graphs over the same
record graph (`hypergraph views add policy`), each reconciled independently; the
state graph is simply the first, mandatory one (SPEC: Views).

Concretely: on a mature project, cold-start orientation over an append-only DAG means
traversing thousands of nodes. With Hypergraph, a fresh agent reads the frontier in
a handful of tool calls (≤ ~6 in our own use — whether that beats plain git on real
work is an open benchmark question) and follows provenance slugs into the record
graph only where the task demands history.

How it stays coherent with many parallel agents: knowledge lands **record-first** —
every record node declares its `## State Impact` (or `none: <reason>`), and a separate
single-writer **reconcile** pass folds declared impacts into the state graph behind an
append-only high-water mark. Nobody edits state inline. Forward work follows the same
rule: new directions (including Operator directives) enter as decision record nodes
whose impacts open `Status: open` state nodes — the frontier carries intent as claims
about gaps, never as task lists.

## Why "hypergraph"

Because of what connects the two graphs, and that connection is the actual bet.

Every state node cites the record nodes it derives from. One claim about the world is
answerable to *many* pieces of evidence at once, and one piece of evidence bears on
*many* claims — so the citation structure is not a tree or a second DAG. Its edges join
sets of nodes to sets of nodes, across two graphs. That is a hypergraph, and it is what
makes a claim auditable: you can always ask "what is this believed on the strength of",
and get back a set you can read.

**The two halves are at very different stages, and it is worth being honest about
which is which:**

- **The record graph is established practice.** An append-only, causally-parented log
  of what was done and why is a lab notebook, an ADR log, an experiment tracker. We are
  implementing a known good idea carefully, not inventing one.
- **The state graph — and the hypergraph that falls out of it — is the novel part, and
  it is under active development.** A single-writer distillation that stays small while
  its evidence base grows without bound; negative knowledge as a first-class citizen
  with scope and confidence; a frontier that is falsified by work rather than checked
  off. Whether that projection stays honest at scale, and whether agents actually
  orient better against it than against raw history, is the open research question this
  project exists to answer. It is being tested on live projects — this repo runs on
  itself, and the protocol has been adopted by others — and it is not finished.

If you are evaluating this, treat the record half as engineering and the state half as
a hypothesis with encouraging early results.

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
([mirror.md](docs/internal/mirror.md)).

## Working in parallel

Several agents, a fork and a pull request, a colleague on another machine — the two
graphs already split along the line git merges on, so the rule falls out of the
invariants rather than adding machinery (SPEC: Collaboration):

**Contributors record; the maintainer reconciles.**

The record graph is append-only with one file per node, so concurrent branches produce
new files and merge without conflict — and each record node arrives in the pull request
as a file, so the claim is reviewed beside the code that justifies it. The state graph
has a single writer (I3), so reconcile runs once on the default branch over everything
that merged. Publishing follows the same line: the mirror is a build artifact of the
default branch, so `hypergraph push` stands down at exit 0 on a feature branch or on a
clone whose credentials don't own the mirror. Nobody needs a credential to contribute.

Two workflows in [templates/github-actions/](templates/github-actions/) make it
enforceable: `hypergraph check --since origin/<base>` fails a pull request that changes
files without recording anything, and a publish job refreshes the mirror on merge.

## Dispatch

Parallel work can also be *aimed*: the `hypergraph-dispatch` skill points an agent at
a target — a frontier node, a stated goal, or a region of the state graph — with a
bounded budget of work units. The dispatch begins as a decision record node
(`Dispatch: <target>`), which doubles as an advisory lane claim other dispatches read
to avoid double work; the work arrives as its children; a closure line ends the
lineage. Nothing new to reconcile against — a dispatched agent is a contributor, so
the workflow above already covers it (SPEC: Dispatch and lanes).

The lane itself — an isolated worktree on a `lane/<slug>` branch — is managed by
`hypergraph dispatch open|ls|harvest|close`, the local implementation of a small
provider seam ([backend/lanes.md](backend/lanes.md)): provision, inject, run,
harvest, teardown. Harvest is a git merge; teardown refuses while unharvested. With
no agent command configured, `dispatch open` provisions the lane and prints the
manual steps, exit 0 — the same stand-down posture as `push` with no mirror.

## What ships

- **[SPEC.md](SPEC.md)** — the protocol: invariants I1–I8 + conventions.
- **[skills/](skills/)** — the Claude skills: `hypergraph-init`, `hypergraph-adopt`
  (bring a project with a past under the protocol: legacy-graph import or authored
  prehistory, adoption epoch, AGENTS.md onboarding), `hypergraph-record`,
  `hypergraph-reconcile`, `hypergraph-orient`, `hypergraph-dispatch`.
- **[tools/hypergraph.py](tools/hypergraph.py)** — uv script, and the offline core of
  a two-file CLI: `check` validates the mechanical invariants over JSON graph exports
  (CI-ready, nonzero exit on violations); `render` generates `STATE.md` (frontier
  first, architecture tree below); `export`/`import`/`new`/
  `update` are the storage layer, `hwm` reports the reconciliation frontier,
  `dispatch` manages local lanes, and `upgrade` refreshes an adopted repo's copies of
  the skills and the AGENTS.md block (`--graph` runs the retroactive graph repairs,
  detect-only until `--apply`). The
  optional mirror's networked half (`push`'s executing tail, `sync`'s publish,
  `mirror`) lives in **tools/hypergraph_mirror.py**, loaded lazily — offline
  commands never import it.
- **[templates/](templates/)** — the exact markdown shapes the checker parses.

## Install

```bash
uv tool install hypergraph-protocol
hypergraph skills install          # → ./.claude/skills (project scope)
```

That is the whole install: the CLI from PyPI, and the skills into the repo you
are working in (`--user` puts them in `~/.claude/skills` instead). Nothing to clone,
nothing to fork.

**Updating later takes two commands, because it is two different things:**

```bash
uv tool upgrade hypergraph-protocol   # the CLI — lives outside your repo
hypergraph upgrade                    # the copies — skills, AGENTS.md block, workflows
```

(`hypergraph upgrade --graph` is the third, rarer thing: retroactive *graph* repairs
for a repo that adopted before a capability existed — detect-only until `--apply`,
because those rewrite node files.)

`skills install` writes real files into your repo, so `uv tool upgrade` cannot see
them and they go stale silently. `hypergraph upgrade` refreshes what is already
there — it never installs what is not, so it will not drop CI into a repo that never
had it, and drifted workflows are reported rather than overwritten (`--workflows`
opts in). Your AGENTS.md block gets the same protection: adoption writes
project-specific content inside those sentinels, so a block you have edited is
reported and left alone, with the shipped version named for you to merge against
(`--agents-block` opts in). It also stamps `hypergraph_version:` into the config, which is what lets
`check` tell you which half is behind. Node files themselves need no migration: they
are additive markdown, and an older CLI reads a newer graph.

## Quickstart

Two routes in, depending on whether the project has a past. Both are Claude skills —
run them in a session inside your project repo.

**New project → `hypergraph-init`**: creates both roots, a state skeleton mirroring
your architecture, `.hypergraph/config.yml`, and `STATE.md`.

```bash
#   run hypergraph-init            → roots + state skeleton + config + STATE.md
#   ... do work; run hypergraph-record after each unit of work
#   run hypergraph-reconcile       → fold impacts into state, regenerate STATE.md
#   (fresh session) hypergraph-orient → frontier brief in a handful of tool calls
```

**Existing project → `hypergraph-adopt`**: a repo with real history, an existing
hosted graph, or both. It surveys the repo (git shape, timeline signals, docs,
churn), interviews you for what only you know, then either imports the legacy graph
verbatim (`hypergraph import --fork` preserves node_ids and slugs, so provenance and
the high-water mark stay valid) or authors honest prehistory from the repo itself. It
draws an adoption epoch so legacy nodes are exempt from template compliance, distills
a state graph from what the project actually knows, and installs the AGENTS.md
onboarding. The import is a **fork**: the source graph stays frozen as the archive,
and the repo becomes the continuing graph, owning its whole history with the original
topology. The *archive's* artifacts do not travel — what travels is a repo-relative
path, and those bytes live on someone else's store — so they stay on the archive and
the adopted project says so. Evidence recorded from then on is an ordinary repo file
and travels with the repo. After either route, the loop is the same.

The whole loop, in the repo — no account, no network:

```bash
hypergraph new record --title "Fixed the streaming parser" --body body.md \
    --parent <causal-slug> --impact "<state-slug> — status broken → working" --repo-auto
hypergraph export --config .hypergraph/config.yml     # node files → cache JSON
hypergraph check --record .hypergraph/cache/record.json \
    --state .hypergraph/cache/state.json --config .hypergraph/config.yml
git add .hypergraph/graph                             # the memory travels with the repo
```

Checker and renderer, standalone:

```bash
hypergraph check  --record .hypergraph/cache/record.json --state .hypergraph/cache/state.json
hypergraph render --state .hypergraph/cache/state.json --config .hypergraph/config.yml -o STATE.md
```

### Visualization

Visualization lives outside this package. The contract is the JSON exports: `export`
writes `.hypergraph/cache/{record,state}.json`, and any renderer that reads those
files can draw the graphs — no import across the package boundary, no coupling to
this tool's internals.

The maintained renderer is **hypergraph-viz**, a thin translator built on
[excaligraph](https://github.com/theo-kirby/excaligraph) (MIT): it reads the two
exports and emits an editable Excalidraw scene, every node carrying a `link:`
back to its markdown source.


## Repo map

```
SPEC.md                     the protocol (invariants + conventions + versioning policy)
CHANGELOG.md                releases, and the labels that never shipped
docs/cli.md                 the CLI reference — 16 subcommands, the exit-code table
docs/example.md             a worked walkthrough over the CI-pinned fixture graph
backend/INTERFACE.md        ~10 abstract operations — the portability contract
backend/local-adapter.md    op → node files + hypergraph CLI (git-native; the one impl)
docs/internal/              mirror internals (mirror.md, flywheel.md) — not agent-facing
backend/lanes.md            the lane-provider seam for dispatch (local ships; box is future)
skills/hypergraph-*/        the skills (.claude/skills/ symlinks these)
templates/                  record-node / state-node / config shapes
templates/github-actions/   PR check + publish-on-merge workflows
tools/hypergraph.py         the offline core: checker + renderer + storage + dispatch (uv script)
tools/hypergraph_mirror.py  the mirror's networked half, lazily loaded by the core
tools/fixtures/             test fixtures (clean, violations, local-graph, epoch)
tests/                      pytest suites (checker, storage, mirror, split, dispatch, collaboration, adoption, upgrade)
```

This repo dogfoods itself: see [.hypergraph/config.yml](.hypergraph/config.yml) and
[STATE.md](STATE.md).

### Developing the protocol itself

Only if you are working on *this* repo — adopters never clone it. In a dev checkout
the CLI is `uv run tools/hypergraph.py …` (`[tool.uv] package = false`, so the bare
`hypergraph` does not resolve here), and `./install.sh` symlinks `skills/` into
`~/.claude/skills` so an edit to a skill is live in the next session.

```bash
./install.sh                       # symlink the skills into ~/.claude/skills
uv run pytest tests/               # checker + storage + mirror suites
uv run tools/hypergraph.py sync --config .hypergraph/config.yml
```
