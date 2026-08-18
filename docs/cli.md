# The `hypergraph` CLI

One tool, sixteen subcommands. Adopters get it from
`uv tool install hypergraph-protocol`; in a dev checkout of the protocol repo it
is `uv run tools/hypergraph.py …`. Everything below is offline except `push`,
`sync`'s publish step, and `mirror` — and each of those stands down cleanly
(exit 0, one line) when no mirror is configured.

## Exit codes — the one canonical table

Exit codes are a contract ([SPEC.md → Versioning](../SPEC.md#versioning));
prose output is not.

| Code | Meaning |
|------|---------|
| 0 | Success — including a deliberate stand-down (no mirror configured, wrong branch, nothing to do). |
| 1 | Findings: `check` violations, `push --verify` drift, an unresolvable high-water mark. |
| 2 | Usage or environment error: bad flags, missing config or export, a refused operation (stale `--expect`, record-node edit, install over a live source link). |

## Checking and rendering

- **`check`** — validate the invariants over the two JSON exports
  (`--record`/`--state`, usually with `--config`). Exit 1 on any I2/I4/I5/I6/I7
  violation; warnings (I1 proxies) and info lines never affect the exit code.
  `--since <ref>` adds the branch-mode I1 check — the PR gate: files changed on
  `<ref>...HEAD` with no new record node fail.
- **`render`** — regenerate STATE.md from the state export (`-o STATE.md`;
  stdout without it).
- **`hwm`** — report the reconciliation frontier and the unreconciled nodes
  (read-only). `--tips` prints the record graph's childless tips — what a
  fold-everything reconcile writes; `--suggest` is the pre-0.0.5 migration aid.

## The local backend (node files under `.hypergraph/graph/`)

- **`export`** — node files → `.hypergraph/cache/{record,state}.json`, the
  contract every consumer reads.
- **`import`** — explode export JSON into node files; `--fork` preserves ids
  and slugs verbatim and files the source under `origin:` (the adoption path).
- **`new`** — author a `record` or `state` node file, validated by the real
  checker before anything is written (exit 2 = nothing written). State writes
  require `--reconcile` (the I3 gate); `--impact`/`--none` generate
  `## State Impact`; `--repo-auto` generates `## Repo`.
- **`update`** — replace a state node's body/parents behind a compare-and-swap
  (`--expect <sha>`, from `--print-sha`) and `--reconcile`. Refuses record
  nodes outright — corrections are child nodes.
- **`artifacts`** — `add`/`rm`/`mv`/`ls` a record node's evidence paths
  (repo-relative, order-preserving). Never legal on state nodes.
- **`tags`** — `list`/`add`/`rm` the declared vocabulary in
  `.hypergraph/tags.yml` (never hand-edit it).

## Distribution and repair

- **`skills`** — `skills install` copies the six skills into `./.claude/skills`
  (`--user` for `~/.claude/skills`, `--link` for a dev checkout; re-runnable).
  Under an installed wheel, reference documents install once as a shared
  `hypergraph-references/` payload that each skill links into.
- **`upgrade`** — refresh an adopted repo's *copies* (skills, the AGENTS.md
  sentinel block, workflows) and stamp `hypergraph_version:`. Completes an
  opted-in repo's skill set; never opts a repo in. `--graph [<healer>]` is the
  repair half: typed retroactive graph repairs, detect-only until `--apply`.
- **`adopt`** — the computed facts of an adoption: `--survey`, `--pull`,
  `--init` (mints or adopts roots + writes a valid config), `--marker`,
  `--resolve-prefixes`. The claims stay yours to write.

## Publishing (optional mirror) and dispatch

- **`push`** — publish committed node files to the configured mirror, one-way.
  `--plan` (network-free), `--verify` (drift check, exit 1 on drift),
  `--record-result`, `--dry-run`, `--limit`. No mirror → exit 0, one line.
- **`sync`** — export → render → check → push in one step; stops before
  publishing if `check` finds violations. The one verb the skills gate on.
- **`mirror`** — diagnostics and plumbing: `doctor`, `roots [--mint]`, `pull`.
- **`dispatch`** — local lanes for dispatched agents: `open` (mint a worktree
  lane), `ls` (lanes + live claims), `harvest` (bring a lane's commits home),
  `close` (tear down; refuses unharvested work without `--force`).
