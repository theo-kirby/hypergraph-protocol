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

## Workflow

1. Read `.hypergraph/config.yml` → state root `node_id`/`slug`. (Local file reads
   don't count against the budget.)
2. `flywheel_get_node_tree` on the state root — one call usually yields the whole
   state-graph topology (it is small by design).
3. `flywheel_get_node` on the state root (HWM + overview) and on each **frontier**
   node — status `open`, `broken`, or `blocked` (SPEC I6). Prefer frontier nodes over
   `working` ones; read `working` bodies only if budget remains and they're relevant
   to the user's question.
4. **Orientation brief** (the deliverable):
   - One line: project, reconciled-through HWM + timestamp, frontier size.
   - Frontier items ranked `broken` → `blocked` → `open`, each with status, claim
     summary, relevant negative knowledge, and its `## Provenance` slugs as the
     **deep-dive pointers** — follow a slug into the record graph
     (`flywheel_resolve_node_slug` → `flywheel_get_node`) only when the task at hand
     needs that history.
   - Flag staleness: if the HWM timestamp is old or the user mentions work not
     reflected in state, recommend hypergraph-reconcile.

## Fallback (no MCP)

If Flywheel MCP is unavailable, read `STATE.md` in the repo — same content, one file
read, possibly stale (its header says when it was reconciled). Say you used the
fallback and how stale it might be.

## Guardrails

- Read-only: no commits, no leases, no tags, no sharing changes.
- Stay in the state graph until you have a concrete reason to open a record node; the
  budget exists to keep cold-start cost flat as the record graph grows.
- Don't re-summarize the whole record history — the brief is about *now* and *next*.
- If the checker/STATE.md and live nodes disagree, trust live nodes and say so.
