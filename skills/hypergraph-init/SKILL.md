---
name: hypergraph-init
description: Initialize the Hypergraph two-graph protocol (record graph + state graph) for a project, on either the local git-native backend or Flywheel. Creates both roots, seeds a state skeleton mirroring the architecture, writes .hypergraph/config.yml, and generates STATE.md.
---

# Hypergraph Init

Sets up the [Hypergraph protocol](references/spec.md) for a project: an append-only
**record graph** and a small distilled **state graph**, with cross-graph provenance in
markdown.

## Backend choice

Init is where a project's `backend:` is decided; every other skill just reads it.

- **`local`** ([local-adapter.md](references/local-adapter.md)) — markdown node files
  committed in the repo. No MCP, no account; the graph travels with the repo and works
  offline. **Default when Flywheel MCP is unavailable**, and a fine default otherwise.
- **`flywheel`** ([flywheel-adapter.md](references/flywheel-adapter.md)) — Flywheel MCP
  as the source of truth. Recommended when you want hosting, cloud agents, or a shared
  graph across repos.
- **`local` + `mirror: flywheel`** — both: local canonical, Flywheel a regenerable
  projection refreshed at the end of each reconcile.

Ask the user which they want when MCP is available; otherwise say you are using `local`.

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
2. **Create the two roots** (parentless; adapter §1):
   - `<project> — record`: content briefly describes the append-only log discipline.
   - `<project> — state`: content = project overview + a `## Reconciliation` section
     with `high_water_mark: none` and `reconciled_at:` now (SPEC I5).
   ```bash
   # local — the CLI generates the state root's Reconciliation block; each call
   # prints the minted slug as its first stdout field
   hypergraph new record --root --title "<project> — record" --body record-root.md
   hypergraph new state  --root --title "<project> — state"  --body overview.md --reconcile
   # flywheel — flywheel_commit_new_node twice, parent_ids: []
   ```
3. **Seed the state skeleton**: one child of the state root per architecture component
   (`hypergraph new state --parent <state-root> --status open --prov "…" --reconcile`,
   or `flywheel_commit_new_node` with `parent_ids: [state root]`). Each follows the
   state-node template with `Status: open`, a one-line `## Current` describing intent,
   `## Negative knowledge` = `None yet.`, and `## Provenance` citing the init record
   node's slug (create record node #1 first if you need the slug — order steps 3/4
   accordingly).
4. **Record node #1** (`hypergraph-record` discipline): child of the record root titled
   "Project initialized under Hypergraph", documenting the chosen architecture, with
   `## State Impact` listing `- target: <each seeded state slug> — seeded, status open`
   (or `NEW` lines if you created record node #1 before the skeleton).
5. **Advance the HWM** through record node #1 so `high_water_mark:` names its slug:
   `hypergraph update <state-root> --body root.md --expect $(hypergraph update
   <state-root> --print-sha) --reconcile` (local-adapter §7), or lease + commit the state
   root (flywheel-adapter §7).
6. **Write `.hypergraph/config.yml`** in the target repo from
   [config.example.yml](references/config.example.yml): project name, both roots'
   `node_id` + `slug`, the chosen `backend:` (+ `graph_dir:` for `local`, `mirror:` if
   both). Add `.hypergraph/cache/` to the repo's `.gitignore` — and for `local` make
   sure `.hypergraph/graph/` is **not** ignored; it is the project's memory.
7. **Export + render**: `hypergraph export --config .hypergraph/config.yml` (local) or
   `flywheel_export_subgraph` (`include_descendants: true`) per root (flywheel) →
   `.hypergraph/cache/{record,state}.json`, then:
   ```
   uv run <hypergraph repo>/tools/hypergraph.py render --state .hypergraph/cache/state.json --config .hypergraph/config.yml -o STATE.md
   uv run <hypergraph repo>/tools/hypergraph.py check --record .hypergraph/cache/record.json --state .hypergraph/cache/state.json --config .hypergraph/config.yml
   ```
   The check must exit 0 before you report success.
8. **Commit** (`local`): `git add .hypergraph/config.yml .hypergraph/graph STATE.md`.
   **Adopting an existing Flywheel project instead?** Export both graphs to
   `.hypergraph/cache/`, then `hypergraph import --record … --state …` — node_ids and
   slugs are preserved verbatim, so the existing config stays valid (local-adapter
   §Bootstrapping).

## Guardrails

- Never link the two roots with a graph edge; the graphs stay topologically disjoint
  (SPEC: pointers are markdown slugs, not edges).
- Keep the skeleton small — components, not tasks. A handful of `open` nodes is a
  healthy day-one frontier.
- `flywheel`: `commit_new_node` payloads need all six `repo_context` keys (null is
  fine) — see adapter §1. `local`: `--reconcile` is required for every state write
  (SPEC I3), and init is one of the two places allowed to pass it.
- Report the created slugs (both roots + skeleton) to the user; they are permanent
  handles.
