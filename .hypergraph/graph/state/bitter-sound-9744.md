---
node_id: 47030781-d078-5801-b4ae-d12ecc5d988f
slug: bitter-sound-9744
title: Field dogfooding
created_at: '2026-08-07T10:57:16.723412+00:00'
parents:
- cool-king-8586
summary: a3go (mode A, re-mirrored) + tbinn (mode B) live; acceptance loop held; five field defects fixed; third surface opening — cloud-box adoption with a control group.
flywheel:
  node_id: 47030781-d078-5801-b4ae-d12ecc5d988f
  slug: bitter-sound-9744
  revision: 4
  pushed_at: '2026-08-09T10:15:16+00:00'
  content_sha256: 028b363b21e19f978795f24dc250c6d67a8a02260cc53c505c49c6a340579b7c
---
Status: working

## Current

- Both dogfooding targets are live under the protocol [rec: vast-sky-3964]: **a3go** adopted mode A — 108-node legacy Flywheel graph imported verbatim as the fork, legacy graph frozen as archive, check 0/0 with 107 nodes epoch-exempt, honest distilled frontier, verified mirror on fresh roots [rec: humble-clover-7048]; **tbinn** adopted mode B — three authored prehistory nodes, check 0/0, frontier led by a genuinely broken node (the first in any hypergraph deployment), full verified mirror [rec: stormy-dew-2969].
- The acceptance bar is met: a cold-start agent in a3go, given only the repo's AGENTS.md, completed orient (6 calls, citing pre-adoption evidence) → genuine frontier work → causally-parented record with valid impacts → librarian reconcile → mirror push + verify clean, with zero protocol violations [rec: fond-tree-4727].
- Dogfooding paid for itself: four protocol defects were found and fixed in the field — manual mirror pushes can deviate from plan bytes invisibly to `push --plan` (caught by verify); verify falsely flagged config-declared mirror roots (exemption added); the adopt skill's mode-B marker rule prescribed `--root`, which the CLI correctly refuses (rule corrected to parent on the newest prehistory node); `hypergraph new state` accepted pre-scaffolded bodies, duplicating template sections (guard added) [rec: careful-harbor-3902] [rec: humble-clover-7048] [rec: stormy-dew-2969].
- a3go's mirror was re-published in full and is the first adopted project whose mirror is verified on its own merits: 108 imported nodes created under roots this account owns, original topology restored, archive lineage at the record root, `push --verify` exit 0 against the two mirror roots **alone**. Its mirror record graph went from 4 nodes to 112; 108 creates ran with zero 429s, results recorded in batches of 20 [rec: northern-willow-0469].
- A fifth field defect, and the largest: the mode-A mirror had been a stub since adoption — 105 of 108 imported nodes were never pushed, and `push --verify` reported clean because the archive roots were spliced into the export it was given [rec: copper-moss-3669] [rec: northern-willow-0469]. tbinn is unaffected: mode B has no `origin:` and already mirrored in full.
- Still unexercised by field use: `superseded` status, staleness reporting between long reconcile gaps, and parallel-agent recording [rec: patient-limit-9007].
- A third dogfooding surface is opening: agents on **fresh cloud boxes** adopting the protocol from PyPI with no prior context, as one arm of a controlled comparison against git and Flywheel (protocol-benchmark-4417). Unlike a3go and tbinn this one has a **control group**, so it can measure whether the protocol helps rather than only whether it holds. First evidence in hand: the published 0.0.2 installs and runs on a bare box via the real adopter route [rec: twilight-wood-1934].

## Negative knowledge

- [scope: mirroring an adopted project | confidence: high | evidence: northern-willow-0469] any node mirrored before its true parent existed on the mirror gets parented to the mirror root as a placeholder, and nothing later repairs it. On a3go this was two nodes, not just the epoch boundary the design anticipated. A topology audit — every local node's parent slugs mapped through `flywheel:` ids and compared against the mirror's `incoming_ids` — is what finds them; the epoch marker alone is not the whole set.

## Provenance

- patient-limit-9007 — Operator directive opening this gap
- vast-sky-3964 — dogfooding targets and adoption modes chosen; acceptance bar defined
- humble-clover-7048 — a3go adoption landed (mode A)
- stormy-dew-2969 — tbinn adoption landed (mode B)
- fond-tree-4727 — acceptance loop held; thrust decided
- copper-moss-3669 — stub-mirror defect measured on a3go and diagnosed
- northern-willow-0469 — a3go re-mirrored in full; first mirror-only verify
- twilight-wood-1934 — cloud-box adoption arm opened; published CLI proven on a fresh box
