---
name: hypergraph-record
description: Commit a unit of research/engineering work to a Hypergraph record graph with a State Impact declaration. Use during or after any meaningful unit of work in a project with .hypergraph/config.yml. Never writes state nodes.
---

# Hypergraph Record

The commit discipline for the append-only **record graph**. Every unit of work becomes
one record node with a declared state impact; a separate reconcile pass folds impacts
into the state graph. Protocol: [spec.md](references/spec.md); backend recipes:
[flywheel-adapter.md](references/flywheel-adapter.md).

## When To Use

- During/after any unit of work (experiment, decision, fix, dead end) in a project
  that has `.hypergraph/config.yml`.
- Dead ends and failures especially — they are the raw material for negative knowledge.
- When the Operator or an agent sets a new direction (feature, research thrust,
  constraint) **before any work exists**: record a decision node capturing the
  intent, constraints, and rationale, attributed to its source, with `## State
  Impact` declaring `NEW <node>` (or deltas) so reconcile opens the gap on the
  frontier. Intent enters through the record graph like everything else (SPEC:
  Forward work).

Not for editing state nodes (that is reconcile's job — SPEC I3) or for orientation
(use hypergraph-orient).

## Workflow

1. Read `.hypergraph/config.yml` for the record root.
2. **Choose the parent by causal relation** (SPEC conventions): the record node whose
   result/decision this work follows from. Find it via STATE.md provenance slugs or
   `flywheel_get_node_children` from the record root. Branch from the root only for a
   genuinely independent new workstream — no root-spam. Extra causal parents:
   `flywheel_add_parent`.
3. **Compose content** from [record-node.md](references/record-node.md) — exact
   headings `## What / ## Why / ## Method / ## Result / ## Repo / ## State Impact`.
   `## Repo` and the payload's `repo_context` carry the current commit SHA when code
   is involved.
4. **Always declare `## State Impact`** (SPEC I2), one of:
   - `- target: <state-slug> — <delta>` per affected state node (status flips, new
     claims, new negative knowledge, supersessions);
   - `- target: NEW <kebab-name> — <delta>` when reconcile should create a state node;
   - `none: <reason>` when current state truly doesn't change.
   Look up real state slugs in STATE.md — a wrong target fails `check`.
5. **Commit** with `flywheel_commit_new_node` (adapter §2).
6. **Attach evidence** when it exists (logs, plots, data): prepare → upload raw bytes
   → finalize (adapter §9), each artifact with a real title.
7. Tell the user the new slug and its declared impact. If impacts are piling up,
   suggest running hypergraph-reconcile.

## Guardrails

- **Never write state nodes** (SPEC I3) — no lease, no commit on anything in the state
  graph, even for a "trivial" status flip. Declare the impact instead.
- Record nodes are immutable once committed: follow-ups and corrections are new child
  nodes, not edits.
- One node per unit of work — don't batch a week into one node, don't split one
  experiment into five.
- Reproduction-grade content (`## Method` / `## Result`): numbers, commands,
  interpretation — enough for a third party to audit (SPEC I8 depends on it).
- Write limits: 120 creates/min, 2000/day; on 429 honor `Retry-After` and retry the
  same call (adapter: write limits).
