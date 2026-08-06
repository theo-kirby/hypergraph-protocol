---
name: hypergraph-init
description: Initialize the Hypergraph two-graph protocol (record graph + state graph) for a project, backed by Flywheel. Creates both roots, seeds a state skeleton mirroring the architecture, writes .hypergraph/config.yml, and generates STATE.md.
---

# Hypergraph Init

Sets up the [Hypergraph protocol](references/spec.md) for a project: an append-only
**record graph** and a small distilled **state graph**, with cross-graph provenance in
markdown. Backend recipes: [flywheel-adapter.md](references/flywheel-adapter.md).

## When To Use

- The user wants to start tracking a project with Hypergraph.
- A repo has no `.hypergraph/config.yml`.

Do NOT use on a repo that already has `.hypergraph/config.yml` — that project is
initialized; use hypergraph-record / hypergraph-reconcile / hypergraph-orient instead.

## Workflow

1. **Interview (short).** Ask only what you cannot infer from the repo:
   - Project name (default: repo directory name).
   - Architecture outline: the 3–8 top-level components/capabilities the state graph
     should mirror (propose a list from the repo layout; let the user edit it).
2. **Create the two roots** via `flywheel_commit_new_node` (parentless; see adapter §1):
   - `<project> — record`: content briefly describes the append-only log discipline.
   - `<project> — state`: content = project overview + a `## Reconciliation` section
     with `high_water_mark: none` and `reconciled_at:` now (SPEC I5).
3. **Seed the state skeleton**: one child of the state root per architecture component
   (`flywheel_commit_new_node` with `parent_ids: [state root]`). Each follows the
   state-node template with `Status: open`, a one-line `## Current` describing intent,
   `## Negative knowledge` = `None yet.`, and `## Provenance` citing the init record
   node's slug (create record node #1 first if you need the slug — order steps 3/4
   accordingly).
4. **Record node #1** (`hypergraph-record` discipline): child of the record root titled
   "Project initialized under Hypergraph", documenting the chosen architecture, with
   `## State Impact` listing `- target: <each seeded state slug> — seeded, status open`
   (or `NEW` lines if you created record node #1 before the skeleton).
5. **Advance the HWM** through record node #1: lease + commit the state root
   (adapter §7) so `high_water_mark:` names record node #1's slug.
6. **Write `.hypergraph/config.yml`** in the target repo from
   [config.example.yml](references/config.example.yml): project name, both roots'
   `node_id` + `slug`. Add `.hypergraph/cache/` to the repo's `.gitignore`.
7. **Export + render**: `flywheel_export_subgraph` (`include_descendants: true`) for
   each root → `.hypergraph/cache/{record,state}.json`, then:
   ```
   uv run <hypergraph repo>/tools/hypergraph.py render --state .hypergraph/cache/state.json --config .hypergraph/config.yml -o STATE.md
   uv run <hypergraph repo>/tools/hypergraph.py check --record .hypergraph/cache/record.json --state .hypergraph/cache/state.json --config .hypergraph/config.yml
   ```
   The check must exit 0 before you report success.

## Guardrails

- Never link the two roots with a graph edge; the graphs stay topologically disjoint
  (SPEC: pointers are markdown slugs, not edges).
- Keep the skeleton small — components, not tasks. A handful of `open` nodes is a
  healthy day-one frontier.
- `commit_new_node` payloads need all six `repo_context` keys (null is fine) — see
  adapter §1.
- Report the created slugs (both roots + skeleton) to the user; they are permanent
  handles.
