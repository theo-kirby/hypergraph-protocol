## Your memory system: Flywheel

Your memory is **Flywheel** — a graph-based system for tracking research work,
decisions, and evidence over time. Think "git for science": a DAG of research
**nodes** carrying ideas, plans, experiments, and the artifacts that back them
up. Record everything you do there, so your work is traceable and replicable by
anyone who reads the graph later.

Your interface is the **Flywheel MCP tools**, already wired into this session and
namespaced `mcp__flywheel__*`.

**Read the live contract first**, before anything else — it is self-describing
and always current:

- `flywheel_get_contract` — the operation catalog and node model.
- `flywheel_get_contract_section` — deep dives, in this order: `graph` →
  `stage_commit` → `artifacts` → `sharing`.

If this document ever disagrees with the contract, **the contract wins**.

### The unit of record: a node

A node is one unit of research. Its body is exactly three fields:

- **`title`** — a short, specific, self-describing line (~60–80 chars).
- **`content`** — the substance, in Markdown. A reliable skeleton is
  **Hypothesis → Setup → Results (with deltas vs the baseline) → Interpretation**.
  Dense, about 1k chars, not an essay.
- **`summary`** — 1–3 sentences stating the concrete change **relative to this
  node's parent** and the outcome, so a reader can follow the step from the text
  alone. Include a verdict: GREEN / RED / REFUTED.

Do **not** write typed fields like `kind`, `node_type`, or `hypothesis` — they
were removed and the server rejects them. Whether a node is an idea, a plan, or
an experiment is conveyed in your prose.

Two kinds of node are both first-class. **Insight nodes** — an observation, a
plan, a decision and its rationale, a branch point, a synthesis — legitimately
have no artifacts, and that is correct. **Empirical nodes** — a concrete run with
a measured outcome — **must** carry at least one finalized artifact.

### Structure: build a graph, not a chain

The most common failure is a flat linear chain, each node the sole child of the
last. That throws away the point of the system. Encode the **real causal
structure** of your research:

- **`flywheel_commit_new_node`** — create a node. `parent_ids` is what it
  genuinely builds on, and it can be more than one.
- **`flywheel_branch_node`** — fork an alternative line of inquiry. Explore
  option A versus option B by branching twice from the same parent, so they sit
  side by side.
- **`flywheel_merge_nodes`** / **`flywheel_add_parent`** — reconcile threads, and
  cross-link a node to all of its real lineage. This is what makes it a DAG.

The shape that works: a **shallow trunk that branches wide into experiment
leaves, with periodic synthesis nodes that merge siblings**. When your next step
builds on an earlier hub rather than the last thing you ran, parent it on the
hub. Merge to **synthesize, not to collect** — every merge must state what the
combination *means*.

Use **tags** to keep a growing graph legible: define a tag once on the root
(`flywheel_create_node_tag`), then assign (`flywheel_set_node_tag_assignments`)
along `Cluster: <family>`, `outcome:GREEN|RED`, and `kind:…`.

### The loop you run

1. **Orient.** Read the contract, then traverse the DAG around your target:
   `flywheel_list_nodes` (`owners:["me"]`), `flywheel_get_node`,
   `flywheel_get_node_children` / `_parents` / `_tree`.
2. **Frame the step as a node** — insight or empirical — and decide its parents.
3. **Run it**, writing outputs under `~/research/artifacts/`.
4. **Attach artifacts before you commit an empirical node.** Three calls:
   `flywheel_prepare_artifact_uploads` → HTTP **PUT** the raw bytes to the
   returned `upload_url` with the returned headers (expect **202**) →
   `flywheel_finalize_artifact_uploads`. Attach the metrics and a `run.json`
   recording the exact command, environment, and seeds.
5. **Commit** with `flywheel_commit_new_node`.
6. **Make it public** — `flywheel_set_sharing_for_nodes`, `sharing_mode: public`.
   New nodes are not public by default.
7. **Verify, then iterate.** Re-read the node; confirm the artifact count is
   non-zero and the body is written.

To **edit** an existing node: `flywheel_get_node` (note its `revision`) →
`flywheel_acquire_stage_lease` → `flywheel_commit_node` with
`base_committed_revision`. On a `409`, re-read and retry.

### Rules

- **Empirical nodes are never empty.** Zero artifacts is a failed unit of work
  even if the code ran. Insight nodes correctly have none.
- **Every node has a written body.** A title is not enough.
- **Build a graph.** Real parents, branches for alternatives, synthesis nodes.
- **Everything public.** A private node is invisible and does not count.
- **Commit as you go** — one node per coherent step, not one dump at the end.
- **Record negative results as nodes.** A refuted hypothesis is a valid node.
- **Stop cleanly**: finish with a multi-parent synthesis node saying what you
  found and what a follow-up should try.
