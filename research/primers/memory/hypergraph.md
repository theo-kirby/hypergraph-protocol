## Your memory system: the Hypergraph protocol

Your memory is **two graphs**, kept as markdown files committed in your own git
repo, driven by the `hypergraph` CLI (installed; run `hypergraph --help`).

- The **record graph** is append-only: everything that happened, one node per
  unit of work, each causally parented to the work it followed from. Nodes are
  immutable — corrections are new child nodes, never edits.
- The **state graph** is small and distilled: what is *true now*, including the
  frontier of open, broken, and blocked work, plus **negative knowledge** — what
  you know does not work, and why.

`STATE.md` is a generated snapshot of the state graph. The split is the whole
point: the record grows forever, but the cost of orienting stays flat, because
you orient on the state graph and follow provenance slugs into history only when
you need that history.

### Already set up

Both graphs exist and are empty: `.hypergraph/` holds the config and one root per
graph, on the `local` backend. Commit that directory — the node files are the
memory and they travel with the repo. Build the state skeleton as you go: a state
node per component of the work (say 3–6), each `Status: open` with a one-line
intent, written in a reconcile pass.

### The unit of record: a record node

One node is one meaningful unit — a feature, a fix, an experiment, a **dead end**,
a decision. Sections, in this order:

- **`## What`** — what you did, concretely.
- **`## Why`** — what it followed from, and the reasoning.
- **`## Method`** — commands, settings, seeds. Enough for a third party to redo it.
- **`## Result`** — the numbers and what they mean. Negative results included.
- **`## Repo`** — the commit this work sits on.
- **`## State Impact`** — **required, always** (see below).

Create one with:

    hypergraph new record --title "…" --body body.md --parent <slug> \
        --repo-auto --impact "<state-slug> — <what changed about it>"

Then `hypergraph export` and **commit the node file**. A node that is not
committed is invisible — the checker cannot see work that lives only in the
working tree.

**Choose the parent by causal relation** — the node whose result or decision this
work follows from, not simply the last node you made. That is what makes the
record a graph instead of a chain. A genuinely independent workstream branches
from the root; nothing else should.

### State Impact — the rule that ties the graphs together

Every record node declares how it changes what is true, as one or more lines:

    - target: <state-slug> — <the delta: status flip, new claim, new negative knowledge>
    - target: NEW <kebab-name> — <delta>        # when a new state node is needed
    - none: <reason>                            # when state genuinely does not change

**Never write or edit a state node yourself.** You *declare* impacts; a separate
reconcile pass folds them in. This is the protocol's single-writer rule, and it
is what keeps the state graph from drifting into a second, contradictory record.

### The loop you run

1. **Orient.** Read `STATE.md` — the frontier tells you what is open, broken, or
   blocked, with provenance slugs into the record graph. Do this before acting,
   and again whenever you lose the thread.
2. **Do one unit of work.**
3. **Record it** — one record node, causally parented, with its `## State
   Impact`. Do this while it is fresh, not at the end.
4. **Reconcile periodically** (every few nodes, and before you stop): read the
   record nodes past the high-water mark, fold their declared impacts into the
   state nodes, add any new negative knowledge, then advance the high-water mark
   and regenerate `STATE.md`. State-node writes require the `--reconcile` flag —
   that flag is you asserting this is a reconcile pass.
5. **Verify:**

       hypergraph export
       hypergraph check --record .hypergraph/cache/record.json \
           --state .hypergraph/cache/state.json --config .hypergraph/config.yml

   It must report **0 violations**. Fix any it reports before moving on.
6. **Commit and push** the node files with your code.

### Rules

- **Record every unit of work**, especially dead ends and failures — negative
  knowledge is the state graph's most valuable content, and it only gets there
  through a record node.
- **Record decisions before the work exists.** A new direction with no work yet
  is still a record node; that is how intent enters the graph.
- **Never hand-edit `STATE.md`** — it is generated.
- **Never write state nodes outside a reconcile pass.**
- **Record nodes are immutable.** Follow-ups are new children.
- **One node per unit of work.** Do not batch a whole session into one, and do
  not split one experiment into five.
- **`## Method` and `## Result` are reproduction-grade**: numbers, commands,
  interpretation — enough for a stranger to audit.
- **Keep `check` at 0 violations.** A violation means the memory is lying about
  itself.
