---
node_id: e888bcc5-7691-5a34-a6fb-b371166722f1
slug: damp-meadow-9143
title: 'U10: release surface — CHANGELOG, versioning policy, CLI reference, worked example'
created_at: '2026-08-18T12:21:58+00:00'
parents:
- steady-rose-0661
summary: ''
flywheel:
  node_id: 1ab128fc-2eac-5de0-9f31-9b77d0968070
  slug: curly-rain-8834
  revision: 0
  pushed_at: '2026-08-18T12:22:01+00:00'
  content_sha256: 4748925195b6550237d837471bd758b22051c605bcbf3720ddfd9560b03e6e81
  parents_sha256: 91e6820887a79c9edeca10a0f217353c20bcc0bcfa15dce317285438779b7980
  parents:
  - 21627932-5e4d-5a01-b737-b524555ef0c1
---
## What

U10 of the 0.1.0 gate: the release surface an outside adopter was missing — a CHANGELOG with a versioning policy behind it, a single CLI reference with one exit-code table, and a worked example on real nodes.

## Why

The audit's "missing entirely" list: no CHANGELOG, no statement of what a version number promises (is checker strictness stable? are invariant numbers reusable? is `check` prose a contract?), no single CLI reference (exit codes were stated in three places that did not agree), and no worked example — the only real nodes an adopter could study were test fixtures mentioned once.

## Method

- **CHANGELOG.md** (Keep-a-Changelog): `[Unreleased]` holds the gate work and writes down the deferred bump procedure (five synchronized version locations + promoting the heading; test_packaging holds all six); 0.0.11 → 0.0.2 reconstructed from git history and the record graph, with dated entries only for index-verified releases, 0.0.3/0.0.4/0.0.9/0.0.10 noted as never published, and an explicit "0.9.0 — retracted label, never released" entry. New test: the newest *released* heading must equal the pyproject version.
- **SPEC "Versioning"** in Future-work's old slot: a minor bump may change checker strictness (a rule that flags a correct live graph is a defect in the rule — the dogfood test is named as the standing net), the CLI surface, and prose output; stable are invariant numbers (permanent, never reused — I5's v0.0.5 change cited as the precedent for number-keeping migration), exit codes 0/1/2 as a contract, the additive node-file format, and the export JSON shape.
- **docs/cli.md**: all 16 post-cut subcommands, one entry each with notable flags, grouped by function, plus the one canonical exit-code table (0 = success/deliberate stand-down; 1 = findings; 2 = usage/environment). SPEC's Tooling, local-adapter's Failure handling and mirror.md's Verification now point at it instead of restating codes. New test: every `build_parser()` subparser name must appear in docs/cli.md.
- **docs/example.md**: the CI-pinned `tools/fixtures/local-graph/` (3 record + 2 state nodes — prototype, OOM dead end, streaming fix) as a walkthrough: record-node anatomy with the dead end highlighted, state-node anatomy mapping each section to its invariant, export + clean check, one real violation from the violations fixtures, render, and the record→reconcile loop that produced the files. Linked from README's repo map with CHANGELOG and cli.md.

## Result

2 new tests; suite 340 → 342 passed, 2 skipped. `sync`: 0 violations, 0 drift. Six synchronized version locations now held by test; zero places state exit codes without deferring to the canonical table.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 08e731ff510768b84d5226b57cb4c58c306956a7

## State Impact

- target: damp-basin-8974 — distribution gains its release surface: CHANGELOG (sixth test-held version location, 0.9.0 named retracted), docs/cli.md with the one exit-code table, docs/example.md on the CI-pinned fixture
- target: young-wave-9364 — SPEC gains the Versioning section: minor bumps may tighten the checker and reshape the CLI; invariant numbers, exit codes, the additive node format and the export shape are the stable surface
