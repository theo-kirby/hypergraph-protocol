---
node_id: 47030781-d078-5801-b4ae-d12ecc5d988f
slug: bitter-sound-9744
title: Field dogfooding
created_at: '2026-08-07T10:57:16.723412+00:00'
parents:
- cool-king-8586
summary: 'Both targets live: a3go (mode A) + tbinn (mode B) adopted, acceptance loop held with zero violations; four protocol defects found and fixed in the field; superseded/parallel-recording still unexercised.'
flywheel:
  node_id: 47030781-d078-5801-b4ae-d12ecc5d988f
  slug: bitter-sound-9744
  revision: 2
  pushed_at: '2026-08-07T21:24:42+00:00'
  content_sha256: 7e9ac0fe16c2594525877b770b72eed8300fa7adec3cf015d2bcd58ced314b0a
---
Status: working

## Current

- Both dogfooding targets are live under the protocol [rec: vast-sky-3964]: **a3go** adopted mode A — 108-node legacy Flywheel graph imported verbatim as the fork, legacy graph frozen as archive, check 0/0 with 107 nodes epoch-exempt, honest distilled frontier, verified mirror on fresh roots [rec: humble-clover-7048]; **tbinn** adopted mode B — three authored prehistory nodes, check 0/0, frontier led by a genuinely broken node (the first in any hypergraph deployment), full verified mirror [rec: stormy-dew-2969].
- The acceptance bar is met: a cold-start agent in a3go, given only the repo's AGENTS.md, completed orient (6 calls, citing pre-adoption evidence) → genuine frontier work → causally-parented record with valid impacts → librarian reconcile → mirror push + verify clean, with zero protocol violations [rec: fond-tree-4727].
- Dogfooding paid for itself: four protocol defects were found and fixed in the field — manual mirror pushes can deviate from plan bytes invisibly to `push --plan` (caught by verify); verify falsely flagged config-declared mirror roots (exemption added); the adopt skill's mode-B marker rule prescribed `--root`, which the CLI correctly refuses (rule corrected to parent on the newest prehistory node); `hypergraph new state` accepted pre-scaffolded bodies, duplicating template sections (guard added) [rec: careful-harbor-3902] [rec: humble-clover-7048] [rec: stormy-dew-2969].
- Still unexercised by field use: `superseded` status, staleness reporting between long reconcile gaps, and parallel-agent recording [rec: patient-limit-9007].

## Negative knowledge

None yet.

## Provenance

- patient-limit-9007 — Operator directive opening this gap
- vast-sky-3964 — dogfooding targets and adoption modes chosen; acceptance bar defined
- humble-clover-7048 — a3go adoption landed (mode A)
- stormy-dew-2969 — tbinn adoption landed (mode B)
- fond-tree-4727 — acceptance loop held; thrust decided
