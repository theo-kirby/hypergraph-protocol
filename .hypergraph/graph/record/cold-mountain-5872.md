---
node_id: b7bbe771-d8b2-5b03-8ce4-f71c5aba4165
slug: cold-mountain-5872
title: 'Decision: Flywheel becomes opaque — one system for the agent, mechanism moves into the CLI'
created_at: '2026-08-09T11:01:08+00:00'
parents:
- solemn-dawn-6752
- spring-fog-0600
summary: ''
flywheel:
  node_id: ba83e416-2fba-565c-b0ad-695b2947b803
  slug: still-leaf-6768
  revision: 0
  pushed_at: '2026-08-09T11:17:22+00:00'
  content_sha256: 1a62872b63ec014c23f46b7b72d16c41c97756be58e86a4b80972db2582ef258
---
## What

Operator-approved plan (2026-08-09), recorded before the implementing work lands
(SPEC: Forward work). One decision with three consequences:

**Flywheel becomes an implementation detail of the CLI.** `backend: flywheel` is
removed as a choice. The markdown node files under `.hypergraph/graph/` are the only
storage; mirroring to a hosted Flywheel graph becomes optional, one-way, out of band,
and — the point — **invisible to the skills**. The agent learns one system: Hypergraph.
It runs local `hypergraph` commands against local files.

Consequences, landing as phased commits:

1. **P0 — dogfood the skills.** `.claude/skills/hypergraph-*` as committed symlinks;
   fix `skills install` so it cannot clobber them; make AGENTS.md true.
2. **P1–P4 — move the mechanism into the tool.** SPEC `## Backend` → `## Storage`;
   the mirroring prose moves out of the file every skill symlinks and into
   `backend/mirror.md`; `hypergraph push` stops emitting a plan for an agent to
   execute and executes it itself; the five skills lose their backend-dispatch
   preambles; config drops the `backend:` menu; version to 0.0.4.
3. **P5 — sharpen adoption.** Mode A stops needing MCP. New `adopt --survey/--pull/
   --init/--marker/--resolve-prefixes` compute the *facts* an adopting agent currently
   gathers by hand, so its budget goes to judgment instead of mechanics.

## Why

Two problems with one root cause, both measured on this repo this session.

**The agent is forced to hold two mental models.** `.hypergraph/config.yml` has said
`backend: local` since the git-native backend landed [rec: empty-forest-6305 is the
state node; the backend work predates this]. Yet every SKILL.md still opens with a
backend-dispatch preamble, symlinks `backend/flywheel-adapter.md` into `references/`,
and hands the agent MCP recipes, lease → commit → release, 409/429 handling, rate
budgets, batch-of-20 result recording, legend-node lifecycle, and the "never splice
archive anchors into the verify export" trap. `hypergraph-reconcile` step 8 alone is
23 lines of Flywheel choreography; `hypergraph-adopt` step 5 is another 20. That is
protocol-irrelevant mechanism eating the agent's attention, and every line of it is a
chance to get the mirror wrong.

The cost is not hypothetical. [rec: sweet-aspen-3667] burned a round on a mirror push
that authenticated cleanly and then 403'd every write — there is no scope
introspection, so nothing but a write probe can detect it. [rec: solemn-dawn-6752]
burned another round on a mirror that looked missing and was not: the key belonged to
a different account. Both are mechanical checks a tool can run and an agent cannot
reliably remember to.

**The skills are not installed.** `~/.claude/skills/` holds only the eight `flywheel-*`
skills; this repo had no `.claude/` directory at all. Two install mechanisms exist —
`install.sh` and `hypergraph skills install` [rec: spring-fog-0600] — and neither had
ever run against this checkout. Compounding it, `[tool.uv] package = false` means
`uv run hypergraph` never resolves, so every skill line reading `hypergraph new record
…` was unexecutable *in the repo that ships it*. The published path is fine; this was a
dev-checkout-only gap, and it meant the project was not actually dogfooding the
artifact it sells.

## Method

Decision only — no implementation in this node. Design settled in plan mode after live
verification against this repo's own mirror:

- The `flywheel` CLI (`~/.local/bin/flywheel`, npm `@paradigma-inc/flywheel` v0.1.108)
  reaches this repo's mirror record root with `can_write: true, is_owner: true`.
- `flywheel export:subgraph --out FILE` writes exactly the JSON that `hypergraph
  import` and `push --verify --against` already consume. **Zero glue needed.**
- Success JSON goes to stdout; errors are a structured envelope on stderr with rc=2
  carrying HTTP status, server detail, and `max_attempts: 3` — the CLI already retries.
- `flywheel help <cmd> --format=json` returns machine-readable schemas for all 130
  commands.
- `tools/hypergraph.py` never reads the `backend:` key — it appears only in comments
  and in the `origin:` block. **Removing the backend selector costs zero code.**

**Transport decision: shell out to the `flywheel` CLI**, with REST via `urllib` as an
explicit fallback. The CLI owns auth including OS-keychain keys, which a REST client
cannot read at all; it resolves the `/v1` path segment absent from the configured
`baseUrl`; and it handles the undocumented `Idempotency-Key`. This keeps
`tools/hypergraph.py` stdlib-only.

**Two rules make "invisible" real rather than merely "shorter":**

- Push is automatic at reconcile, and `hypergraph push` on a project with **no mirror
  configured exits 0 as a no-op**, never 2. That is what lets the skill step be
  unconditional prose instead of a config test the agent must evaluate.
- Nothing in the mirror path runs unless a mirror was asked for. `check`, `render`,
  `viz`, `export`, `import`, `new`, `update`, `skills` must never resolve credentials,
  touch PATH, or import a network module.

## Result

No implementation yet — this node is the decision. Constraints that bind the work:

- **`tools/hypergraph.py` lines 2036–5172 are generated** by `tools/bundle_viz.py` from
  `tools/viz/*`, and `tests/test_viz.py::test_viz_bundle_in_sync` fails if the constant
  is stale. All new code goes in the 1721–2035 window.
- **SPEC invariants I1–I8 (lines 38–153) are already Flywheel-free and must not be
  touched.** This change is about storage and mechanism, not about the protocol.
- **`backend/INTERFACE.md` survives, re-scoped.** State node `blue-sun-8921` asserts its
  existence as `working`; deleting it would falsify a committed state claim.
- **`backend/flywheel-adapter.md` is demoted, not deleted.** It is the only place
  documenting `repo_context`'s six required keys, `local_temp_node_id`,
  `base_committed_revision` semantics, the 409/429 contract, rate limits, and
  add-parent-before-remove ordering — all of which the new executing `push` needs.

**Known risks.**

- **Duplicate mirror nodes are the only unrecoverable failure** in this design;
  `backend/local-adapter.md` records that duplicates cannot be cleanly merged. The CLI
  transport cannot inject an `Idempotency-Key` header, so idempotency must be owned
  locally by a crash journal that resolves ambiguous creates *by looking* — never by
  blind retry. Build that before pacing.
- **Write scope is not introspectable** — a key can authenticate and still 403.
- **Untyped responses** — every mutating endpoint's success schema in the live OpenAPI
  is literally `{}`. Probe shapes, fail loudly, and never default `revision` to 0:
  `revision: 0` is a real value in this repo's frontmatter, and a wrongly-defaulted 0
  makes every subsequent update 409 forever.
- **Hard dependency on the npm binary** for anyone wanting a mirror. Acceptable only
  because the mirror is opt-in and `backend: local` is complete without it — so the
  degradation path must be *tested*, not assumed.

**Deliberately not built: CLI-generated prose.** No generated prehistory bodies,
`## Current` claims, or negative-knowledge entries. That would produce exactly the
aspirational template-filling adopt's guardrails forbid, and it breaks I8 by
definition — claims nobody derived from evidence they read are not re-derivable. The
CLI computes facts; the agent writes claims.

**Version sequencing noted, not scheduled.** 0.0.4 must not land mid-benchmark-run: arm
C asserts the exact installed artifact, `research/boxlab/arms.py` derives the pin from
pyproject, and bumping between runs makes arms non-comparable [rec: staid-field-2723].

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: cd456a2e69eb1c8b15b2b06bbd333dc1dbe47214

## State Impact

- target: dry-wildflower-2260 — direction set: the five skills lose their backend-dispatch preambles and their references/flywheel-adapter.md symlinks, becoming single-path. Acceptance test for the whole change: grepping the five SKILL.md bodies for flywheel|lease|MCP|429|409 returns zero hits. Also: the skills were never actually installed in this checkout — two mechanisms existed and neither had run.
- target: blue-sun-8921 — direction set: the backend selector is removed. INTERFACE.md survives, re-scoped from 'a choice made at init' to 'the ~10 operations a replacement would satisfy' — portability, not configuration. backend/flywheel-adapter.md is demoted to CLI internals rather than deleted; it is the sole record of the payload contract the executing push depends on.
- target: empty-forest-6305 — direction set: node files become the only storage, and hypergraph push stops emitting a plan for an agent to execute and executes it itself (transport, crash journal, pacing, mirror doctor/roots/pull). Verified prerequisite: flywheel export:subgraph already writes exactly the JSON import and push --verify consume, so no glue is needed.
- target: young-wave-9364 — direction set: SPEC ## Backend becomes ## Storage, framing files as the storage rather than one backend among two. Invariants I1-I8 are already Flywheel-free and are explicitly out of scope for this change.
- target: morning-crane-7863 — direction set: adoption mode A stops requiring MCP, and new adopt affordances (--survey/--pull/--init/--marker/--resolve-prefixes) compute the facts an adopting agent currently gathers by hand. Bounded by a deliberate exclusion: no CLI-generated prose, because generated claims break I8 by definition.
- target: bold-field-1268 — the project was not dogfooding its own artifact: no .claude/ directory existed, so no hypergraph-* skill resolved as a slash command in this repo.
- target: fair-field-3265 — two harness incidents are being converted from remembered lore into mechanical checks: the 403-on-write key [rec: sweet-aspen-3667] becomes a write probe, and the wrong-account mirror [rec: solemn-dawn-6752] becomes an account-id assertion in hypergraph mirror doctor.
