---
name: hypergraph-orient
description: Cold-start orientation for a Hypergraph project - land on the state graph, read the frontier (open/broken/blocked), and produce an orientation brief with provenance slugs for deep dives. Read-only, budget about 6 tool calls.
---

# Hypergraph Orient

The read-only landing path for a fresh agent: state root → frontier → orientation
brief, in **≤ ~6 tool calls**. The record graph exists precisely so you do *not* have
to traverse it to know what is true now. Protocol: [spec.md](references/spec.md).

## When To Use

- Starting a session on a project that has `.hypergraph/config.yml`.
- The user asks "where were we?", "what's broken?", "what should I work on?".

Not for writing anything — this skill mutates nothing.

## Backend dispatch

Read `backend:` from `.hypergraph/config.yml` — it decides which workflow below applies.
`local` → [local-adapter.md](references/local-adapter.md); `flywheel` →
[flywheel-adapter.md](references/flywheel-adapter.md). A missing key means `flywheel`.

## Workflow — `local` backend

The graphs are files in the repo, so orientation costs no tool budget at all:

1. Read `.hypergraph/config.yml` → `graph_dir` and the state root slug.
2. Read `STATE.md` — frontier first, architecture tree below, with the reconciled-through
   HWM in the header. That is the whole brief's raw material.
3. Read `.hypergraph/graph/state/<slug>.md` for the frontier nodes you need in full
   (negative knowledge, provenance slugs). Deep-dive pointers are just
   `.hypergraph/graph/record/<slug>.md`.
4. Staleness here is git, not export lag: if `git status` shows uncommitted node files
   or `STATE.md` predates the newest record file, say so and recommend
   `hypergraph export` + hypergraph-reconcile. Skip to **Orientation brief** below.

## Workflow — `flywheel` backend

1. Read `.hypergraph/config.yml` → state root `node_id`/`slug`. (Local file reads
   don't count against the budget.)
2. `flywheel_get_node_tree` on the state root — one call usually yields the whole
   state-graph topology (it is small by design).
3. `flywheel_get_node` on the state root (HWM + overview), then one
   `flywheel_get_node_children` on it (`projection: "core"`) — a single page usually
   returns every component node's full body, statuses and provenance included, which
   beats per-node `get_node` calls. (Don't retry `get_node_tree` with
   `projection: "full"` for bodies — it returns topology-only payloads.) Prefer
   frontier nodes — status `open`, `broken`, or `blocked` (SPEC I6) — over `working`
   ones; dig into `working` bodies only as budget and relevance allow.
## Orientation brief (the deliverable, both backends)

- One line: project, reconciled-through HWM + timestamp, frontier size.
- Frontier items ranked `broken` → `blocked` → `open`, each with status, claim
  summary, relevant negative knowledge, and its `## Provenance` slugs as the
  **deep-dive pointers** — follow a slug into the record graph
  (`.hypergraph/graph/record/<slug>.md`, or `flywheel_resolve_node_slug` →
  `flywheel_get_node`) only when the task at hand needs that history.
- Flag staleness: if the HWM timestamp is old or the user mentions work not
  reflected in state, recommend hypergraph-reconcile.

## Fallback (no MCP, `flywheel` backend)

If Flywheel MCP is unavailable, read `STATE.md` in the repo — same content, one file
read, possibly stale (its header says when it was reconciled). Say you used the
fallback and how stale it might be. Under the `local` backend this is not a fallback:
the repo *is* the graph, so nothing is missing (see local-adapter §5).

## Guardrails

- Read-only: no commits, no leases, no tags, no sharing changes. Under `local`, no
  `hypergraph new`/`update`/`export` either — orientation writes nothing.
- Stay in the state graph until you have a concrete reason to open a record node; the
  budget exists to keep cold-start cost flat as the record graph grows.
- Don't re-summarize the whole record history — the brief is about *now* and *next*.
- If the checker/STATE.md and live nodes disagree, trust live nodes and say so. Under
  `local`, the node files are the live nodes; STATE.md is the derived snapshot.
