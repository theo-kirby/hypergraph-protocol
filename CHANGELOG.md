# Changelog

All notable changes to hypergraph-protocol. The format follows
[Keep a Changelog](https://keepachangelog.com/); versioning policy is in
[SPEC.md → Versioning](SPEC.md#versioning). Dated entries are releases verified
**from the public index**, not from `dist/` — undated version numbers noted
inline were internal or never published.

## [Unreleased]

Nothing yet.

## [0.0.13] — 2026-08-19

Named views (SPEC: Views): N derived graphs over the record graph. The state
graph becomes "view #1" — one enumeration, one node template, one checker path —
and a project can declare more (`hypergraph views add policy`), each reconciled
independently under its own high-water mark.

### Added
- `hypergraph views ls|add <name> [--md FILE] --reconcile` — declare a named
  view: mints the view root through the usual primitives, seeds its
  `high_water_mark:` with the current record tips (a late-born view starts
  caught up), and appends the `views:` block to config.yml textually.
- View-qualified impact targets (SPEC I2): `- target: <view>/<slug> — <delta>`
  and `- target: <view>/NEW <kebab-name> — <delta>`. Unqualified targets still
  mean the state graph, so every existing record node stays valid.
- Per-view checking and reconciliation: I3 is now "single writer **per view**",
  I4–I7 apply per view, and each view root carries its own `## Reconciliation`
  (I5) with a per-view pending-impact tally in `check`.
- `new <view>`/`update` write view nodes behind the same `--reconcile` gate and
  body-hash CAS as state; `hwm --view <name>` and `render --view <name>` read a
  view's export beside `--state`; `export`/`sync` emit `cache/<view>.json` and
  render each view's optional `md:` snapshot beside STATE.md.
- Config: an optional, `views add`-written `views:` block
  (`views.<name>.root` + optional `views.<name>.md`).

### Changed
- The graph-kind enumeration is config-derived (`graph_kinds(config)`); the
  hardcoded record/state pair survives only as the no-config fallback. A
  project without `views:` behaves byte-for-byte as before (pinned by golden
  tests over the fixture graphs).
- The mirror stays record+state only: named views are rebuildable projections,
  and `push` prints one line noting the skip when views are configured.

### Compatibility
- The node-file format is unchanged and the additive promise holds: an older
  CLI reads a graph that uses views, ignores the `views:` config key, and never
  reads `graph/<view>/`. **One honest exception:** pre-0.0.13 `check` reports a
  view-qualified impact line as an I2 unparseable-line violation. This is
  checker-strictness drift the versioning policy allows, stated plainly: **a
  project that adds views needs ≥0.0.13 tooling; projects without views are
  unaffected in both directions.**

## [0.0.12] — 2026-08-18

The 0.1.0 readiness gate, shipped as 0.0.12 by Operator decision — more work is
planned before the 0.1.0 label is used. The seventh published release.

### Added
- `hwm --tips`: the record graph's childless tips — the frontier a
  fold-everything reconcile writes (reachability semantics, never a timestamp).
- `hypergraph-init` installs the agent onboarding contract (AGENTS.md sentinel
  block, `.hypergraph/AGENTS.md`, skills install + ignore check) — previously
  only adopt wrote it.
- The agents-block gains non-negotiable 5 (record on any branch; reconcile only
  on the default branch) and its gate becomes `hypergraph sync`.
- `CHANGELOG.md`, `docs/cli.md` (the CLI reference and the one canonical
  exit-code table), `docs/example.md` (a worked walkthrough over the CI-pinned
  fixture graph), and SPEC's Versioning section.
- End-to-end tests for `sync` and `hwm`; a live-dogfood regression test that
  checks this repo's own committed graph on every run; a parity test pinning
  `sync`'s hand-built push Namespace against every `push` option.

### Changed
- Checker parsing hardened: fence-aware section splitting, duplicate
  load-bearing headings are violations, provenance/evidence slugs match whole
  tokens only (a URL ending `-1234` is no longer read as a citation), status
  lines tolerate a leading HTML comment.
- Export loading fails with an instruction (exit 2) instead of a traceback on a
  missing or truncated cache; every `created_at` ordering is chronological
  across `Z`/`+00:00`/offset spellings.
- `upgrade` installs skills a release added into any repo that already opted in
  (mode-matched); its doctrine is now "never opts a repo in".
- `skills install --link` is idempotent (`install.sh` can be re-run); a repo
  stamped with the retracted 0.9.0 label is told to re-stamp, never to upgrade
  to a CLI that does not exist.
- The wheel ships each skill reference document once
  (`hypergraph_protocol_data/references/`); installed skills link to the shared
  payload (~348 KB → ~136 KB installed).
- mirror.md and flywheel.md moved to `docs/internal/` (CLI internals, not
  agent-facing); the adopt skill collapsed to one mode-branched procedure with
  the native Mode A order; a ten-item drift sweep aligned the skills, SPEC and
  README with the code.

### Removed
- The `viz` signpost stub and the hidden `heal` alias (use `upgrade --graph`).
- SPEC's speculative Future-work section; dead code (`tag_def`,
  `artifact_abspath`); the unused numpy dev-dependency.

## [0.0.11] — 2026-08-16

The sixth published release, first since 0.0.8.

### Added
- `hypergraph-dispatch`: the sixth skill — aim an agent at a target under a
  bounded budget, claims read from live lanes; `hypergraph dispatch
  open/ls/harvest/close` manages git-worktree lanes (`backend/lanes.md`).
- The agents-block points arriving agents at dispatch for deliberate work.

### Changed
- The mirror's networked half split into `tools/hypergraph_mirror.py`, loaded
  lazily — offline commands never import it, held structurally by a subprocess
  test.
- `heal` folded into `upgrade --graph`: one verb, two polarities (copies write
  by default and are `git checkout`-reversible; graph repairs are detect-only
  until `--apply`).

### Note
- 0.0.9 (the viz cut: visualization left core, the JSON exports became the
  contract) and 0.0.10 were staged internally and never published; their changes
  ship here.

## [0.9.0] — retracted label, never released

Stamped into repos during a clean-slate rename experiment and retracted by
Operator directive: the release is 0.0.11. No artifact with this version was
ever published; `check` recognizes the stamp and directs `hypergraph upgrade`
to re-stamp.

## [0.0.8] — 2026-08-09

### Added
- Digest-guarded AGENTS.md refresh: `upgrade` replaces the sentinel block only
  while its content digest matches one this project shipped
  (`SHIPPED_BLOCK_DIGESTS`); anything else is reported as customized and left
  alone. Fixes the destructive overwrite a real mode-A adoption uncovered.

### Fixed
- Twelve defects found by running a mode-A adoption with no author present.

## [0.0.7] — 2026-08-09

### Added
- `hypergraph upgrade`: refreshes an adopted repo's copies (skills, AGENTS.md
  block, workflows) that `uv tool upgrade` cannot see; `hypergraph_version:`
  stamp in the config so `check` can name which half is stale.

## [0.0.6] — 2026-08-09

### Fixed
- Adoption end to end: mode ordering, the front door, era signals, the
  interview — from the first real adoptions.

## [0.0.5] — 2026-08-09

### Changed
- The protocol became merge-safe: I5's high-water mark is an ancestry frontier
  (multi-tip), never a timestamp cutoff; unreconciled enumeration by
  reachability. `hwm --suggest` migrates pre-0.0.5 graphs.

### Added
- Conflict-marker detection in both graphs; `check --since <ref>` — the
  branch-mode I1 gate for pull requests.

### Note
- 0.0.3 and 0.0.4 were internal version bumps (version unification across
  files; config dropped the backend menu) and were never published.

## [0.0.2] — 2026-08-08

### Added
- First published release. `hypergraph skills install`; the skills ship as
  package data. The protocol's own repo runs under it (record + reconcile
  dogfooding). 0.0.1 was packaged under this name but never reached the index.

[Unreleased]: https://github.com/theo-kirby/hypergraph-protocol/compare/main
