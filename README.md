# Hypergraph

**An agent-native substrate for autonomous research and engineering.**

Agents do not fail at long-running work for lack of capability. They fail because 
their environment has no shape. Hypergraph gives agents a structure to work *in*.
Knowledge has one place to go, being wrong is a first-class result, and an arriving
agent reads **what is true now** instead of everything that ever happened. The unit
of work is a claim with its evidence attached.

## Structure

Every graph is markdown files in the project with frontmatter.

- **The record graph** is the ground truth: an append-only causal DAG of
  experiments, decisions, evidence, implementations, dead ends. Nothing is ever rewritten.
- **Views** are distilled projections over it. The **state graph** is view #1,
  always present: architecture, what works, what is broken or open, 
  and accumulated negative knowledge. More axes can be added as the project
  needs them: `hypergraph views add policy` — each reconciled independently.

**Why "hypergraph":** every view node cites the record nodes it rests on. One claim
answers to many pieces of evidence, and one piece of evidence bears on many claims,
so the citations join *sets to sets* across the graphs. This structure is the
hypergraph. 

## Discipline

Four verbs, held by invariants ([SPEC.md](https://github.com/theo-kirby/hypergraph-protocol/blob/main/SPEC.md))
and a mechanical checker:

1. **Orient**: land on the frontier, not on history.
2. **Record**: every unit of work becomes one causally-parented record node that
   declares its impact on the views. A dead end recorded is worth as much as a
   success.
3. **Reconcile**: a single writer per view folds declared impacts in and advances
   the high-water mark. Nobody edits state inline; that is what aims to keep many
   parallel agents coherent.
4. **Dispatch**: aim an agent at a frontier target with a bounded budget in an
   isolated lane; its claim is advisory and visible to other agents.

Forward work enters the same way: intent lands as a decision record node, and the
frontier carries gaps as claims.

**In parallel:** contributors record, the maintainer reconciles. Record nodes are
one file each, so branches merge without conflict and a pull request carries each
claim beside the code that justifies it. `hypergraph check --since <base>` is the
PR gate: changed files with no record node fail.

## Status

The record half is established practice: a lab notebook as a causal DAG. The
state half is the live hypothesis: whether a distilled projection stays small and
honest while its evidence grows without bound. This repo runs on its own protocol
([STATE.md](https://github.com/theo-kirby/hypergraph-protocol/blob/main/STATE.md)),
and other projects have adopted it; it is not finished.

## Install

```bash
uv tool install hypergraph-protocol
hypergraph skills install          # → ./.claude/skills (project scope)
```

## Quickstart

Both entry points are Claude skills — run them in a session inside your repo:

- **New project** → `hypergraph-init`: both roots, a state skeleton mirroring your
  architecture, config, `STATE.md`.
- **Project with a past** → `hypergraph-adopt`: imports a legacy graph or authors
  honest prehistory, draws an adoption epoch, distills a real state graph.

Then the loop: work → `hypergraph-record` → `hypergraph-reconcile` → commit. A
fresh session starts with `hypergraph-orient`.

```bash
hypergraph new record --title "Fixed the streaming parser" --body body.md \
    --parent <causal-slug> --impact "<state-slug> — status broken → working"
hypergraph sync --config .hypergraph/config.yml    # export → render → check
git add .hypergraph/graph STATE.md                 # the memory travels with the repo
```

## Deeper

| | |
|---|---|
| [SPEC.md](https://github.com/theo-kirby/hypergraph-protocol/blob/main/SPEC.md) | the protocol: invariants I1–I8, conventions, views, versioning |
| [docs/cli.md](https://github.com/theo-kirby/hypergraph-protocol/blob/main/docs/cli.md) | the CLI reference and the exit-code contract |
| [docs/example.md](https://github.com/theo-kirby/hypergraph-protocol/blob/main/docs/example.md) | a worked walkthrough over a small graph |
| [backend/INTERFACE.md](https://github.com/theo-kirby/hypergraph-protocol/blob/main/backend/INTERFACE.md) | the ~10 operations a replacement store would have to satisfy |
| [templates/](https://github.com/theo-kirby/hypergraph-protocol/blob/main/templates/) | the exact markdown shapes the checker parses |

Optional, and outside the protocol proper: `hypergraph push` mirrors the committed
node files one-way to a hosted [Flywheel](https://flywheel.paradigma.dev) graph you
own (your files stay canonical), and any visualizer can read the JSON exports —
the maintained one is hypergraph-viz, built on
[excaligraph](https://github.com/theo-kirby/excaligraph).

### Developing the protocol itself

Adopters never clone this repo. In a dev checkout the CLI is
`uv run tools/hypergraph.py …`, and `./install.sh` symlinks `skills/` into
`~/.claude/skills` so a skill edit is live in the next session.

```bash
uv run pytest tests/
uv run tools/hypergraph.py sync --config .hypergraph/config.yml
```
