# Agent instructions for this repo

This repo runs under its own protocol: **Hypergraph** (see [SPEC.md](SPEC.md)). It
keeps two graphs as markdown files committed under `.hypergraph/graph/` — an
append-only **record graph** (everything that happened) and a distilled **state
graph** (what is true now, including the frontier of open/broken/blocked work).
`.hypergraph/config.yml` holds the graph roots; `STATE.md` is a generated snapshot.
The node files are the source of truth: the graphs travel with the repo, offline.

**The graphs are the project's memory, not app data.** The `.hypergraph/` exports
and STATE.md may look like inputs to the viz/checker tooling — they are also the
record of this project itself, and your work must land in it.

## Non-negotiables

1. **Orient on arrival.** Run the `hypergraph-orient` skill (or read `STATE.md`)
   before starting work — the frontier tells you what's open, broken, or blocked,
   with provenance slugs into the record graph for history.
2. **Record every unit of work.** When you finish a meaningful unit — feature, fix,
   experiment, dead end, decision — run the `hypergraph-record` skill: one record
   node, causally parented, with a `## State Impact` section (SPEC I1/I2). Work
   that exists only in the working tree is invisible to the project's memory; the
   checker cannot detect it. New directions with no work yet are recorded too, as
   decision nodes (SPEC: Forward work).
3. **Never write state nodes** (SPEC I3). Declare impacts; only the
   `hypergraph-reconcile` skill folds them into the state graph. Never hand-edit
   `STATE.md` — it is generated.
4. **Verify before finishing:**
   ```bash
   uv run pytest tests/
   uv run tools/hypergraph.py check --record .hypergraph/cache/record.json \
       --state .hypergraph/cache/state.json --config .hypergraph/config.yml
   ```

## Map

- `SPEC.md` — the protocol (invariants I1–I8 + conventions).
- `skills/hypergraph-{init,record,reconcile,orient,adopt}/` — the workflows.
  **This repo dogfoods them.** `.claude/skills/hypergraph-*` are committed relative
  symlinks into `skills/`, so `/hypergraph-record` resolves in a fresh clone and
  editing `skills/<name>/SKILL.md` edits the live skill. Two consequences: **skills
  load at session start**, so an edit you just made is live only from the *next*
  session; and under a harness that does not read `.claude/skills` at all (pi, for
  one), read `skills/<name>/SKILL.md` directly and follow it — the workflow is the
  file, not the installation.
- `tools/hypergraph.py` — the whole CLI; tests in `tests/`.
- `backend/` — `INTERFACE.md` (the ~10 operations that make the protocol portable),
  `local-adapter.md` (the shipped implementation: node files), `mirror.md` and
  `flywheel.md` (optional one-way mirroring — CLI internals, not agent-facing).

## The CLI

In this checkout: `uv run tools/hypergraph.py …`. `[tool.uv] package = false`, so a
bare `hypergraph` does **not** resolve here — that form is for adopters, who get it
from `uv tool install hypergraph-protocol` plus `hypergraph skills install --user`.
