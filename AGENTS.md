# Agent instructions for this repo

This repo runs under its own protocol: **Hypergraph** (see [SPEC.md](SPEC.md)). It
keeps two graphs in Flywheel — an append-only **record graph** (everything that
happened) and a distilled **state graph** (what is true now, including the frontier
of open/broken/blocked work). `.hypergraph/config.yml` holds the graph roots;
`STATE.md` is a generated snapshot.

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
- `skills/hypergraph-{init,record,reconcile,orient}/` — the workflows (also
  installed in `~/.claude/skills`).
- `backend/flywheel-adapter.md` — Flywheel MCP call recipes (payload shapes,
  lease → commit → release, 409/429 handling).
- `tools/hypergraph.py` — `check` / `render` / `viz`; tests in `tests/`.
