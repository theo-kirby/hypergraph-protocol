---
node_id: aa30d762-519b-5e65-895a-3bb708b6590c
slug: violet-shade-9541
title: 'One verb: heal folds into upgrade --graph, detect-only until --apply'
created_at: '2026-08-16T17:44:16+00:00'
parents:
- gentle-journey-8382
summary: ''
flywheel:
  node_id: 7a839acb-23ac-5abc-b0a7-a06f180beaba
  slug: weathered-pond-3087
  revision: 0
  pushed_at: '2026-08-16T18:24:57+00:00'
  content_sha256: 3adf4206a7bba29c0d02f6284894f649d721261434fd328d6a76909ae366fbd7
  parents_sha256: f1fcde8919e4b2da65a585685fb00580bdd93576f885b5ef5139a717d9cb09f0
  parents:
  - b46159a9-5cf4-5ca4-8f4a-77ec1af3e352
---
## What

Folded `heal` into `upgrade` as `upgrade --graph [HEALER…]` — one verb for "bring
this adopted repo current", two polarities, with the flag naming the boundary.
Bare `upgrade` refreshes *copies* (skills, AGENTS.md block, workflows) and writes
by default, because every effect is `git checkout`-reversible. Everything behind
`--graph` is the repair registry (formerly `heal`): it rewrites node files and may
spend mirror writes, so it stays detect-only until `--apply`. Bare `--graph`
lists the registry, exactly as bare `heal` did. `heal` survives as a working but
hidden alias for the 0.9.x series: dropped from the commands table (no `help=`,
plus `metavar="COMMAND"` on the subparsers so the brace list stops enumerating
it), and it prints a one-line deprecation note to stderr.

## Why

Two verbs for one question — "is this adopted repo current?" — made every adopter
learn a distinction ("copies vs graph content") before they could act on it. The
fold keeps the distinction (it is real: reversibility differs) but moves it into
a flag on the one verb they already run after a release. `upgrade --graph
--dry-run` is a parser error rather than a silent no-op, because `--dry-run`
belongs to the copies half and `--graph` is already detect-only.

## Method

`cmd_upgrade` delegates: `--graph` present → set `args.healer` from it and hand
the parsed namespace to `cmd_heal` unchanged (the upgrade parser gained heal's
flags verbatim — `--apply --all --offline --source --allow-dirty --limit --json
--fail-on-drift --yes`, `--graph-dir`, and the mirror args — reusing its existing
`--repo`/`--config`; `heal_args` lost its own `--repo`, which moved onto the
alias parser directly, so the helper applies to both without duplicate-flag
crashes). All pointer text (upgrade tail, registry listing usage, module
docstring, healing section comment, dry-run hint) now says `upgrade --graph`.
Six new tests in tests/test_heal.py: bare-listing byte-parity with `heal`,
detect-output parity, detect-only-until-apply, alias works + deprecation note on
stderr (and its absence on the real verb), `--graph --dry-run` → SystemExit 2,
and `--help` carries no `heal` row.

## Result

`uv run pytest tests/` — 289 passed, 2 skipped (was 283; +6 fold tests). Manual
smoke: `upgrade --graph` lists the registry at exit 0; `heal` still lists it with
the stderr note; `--help` shows no heal row; the dry-run guard errors with the
polarity explanation.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: e98c5ee27ca3d3176e669374a5e6a3f403ec5e99

## State Impact

- target: retroactive-repair-5104 — the repair registry is now reached as `upgrade --graph [HEALER]`; `heal` is a hidden deprecated alias through 0.9.x; polarity rule stated once: copies write by default, graph repairs are detect-only until --apply
- target: wandering-sun-8831 — CLI surface: one verb for bringing an adopted repo current; suite grows 283→289
