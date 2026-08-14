---
node_id: 47030781-d078-5801-b4ae-d12ecc5d988f
slug: bitter-sound-9744
title: Field
created_at: '2026-08-07T10:57:16.723412+00:00'
parents:
- bold-field-1268
summary: 'Four adopted repos, three not written by this project: both modes proven, the acceptance loop held, six protocol defects found and fixed, and one adoption repaired after the fact rather than re-run.'
flywheel:
  node_id: 47030781-d078-5801-b4ae-d12ecc5d988f
  slug: bitter-sound-9744
  revision: 8
  pushed_at: '2026-08-14T13:37:28+00:00'
  content_sha256: f73fe5b9a9f0d16d6095f9210a66b8505f2981bc84fde4934043e9d8b329f33a
  parents_sha256: 2f1db0ebb42915659081b33dc1f705cda7d93bde03beb050a852b134084e75c2
  parents:
  - a4fad33e-262f-5f4a-8d83-298e76523a0e
---
Status: working

## Current

Repos that adopted the protocol, three of which this project did not write. This is where defects that survive the author's assumptions are found [rec: vast-sky-3964].

- **a3go**, mode A: a 108-node legacy Flywheel graph imported verbatim as the fork, the legacy graph frozen as archive, check 0/0 with 107 nodes epoch-exempt, an honest distilled frontier, and a verified mirror on fresh roots [rec: humble-clover-7048]. **tbinn**, mode B: three authored prehistory nodes, check 0/0, and a frontier led by a genuinely broken node — the first in any deployment [rec: stormy-dew-2969].
- **The acceptance bar is met.** A cold-start agent in a3go, given only the repo's AGENTS.md, completed orient (6 calls, citing pre-adoption evidence) → genuine frontier work → a causally-parented record with valid impacts → librarian reconcile → mirror push and verify clean, with zero protocol violations [rec: fond-tree-4727].
- **Dogfooding paid for itself: six protocol defects were found in the field.** Four came from the first two adoptions — manual mirror pushes deviating from plan bytes invisibly to `push --plan`; verify falsely flagging config-declared mirror roots; the adopt skill's mode-B marker rule prescribing `--root`, which the CLI correctly refuses; and `new state` accepting pre-scaffolded bodies that duplicated template sections [rec: careful-harbor-3902] [rec: humble-clover-7048] [rec: stormy-dew-2969].
- **The fifth and largest**: a3go's mode-A mirror had been a stub since adoption — 105 of 108 imported nodes never pushed, with `push --verify` reporting clean because the archive roots were spliced into the export it was given [rec: copper-moss-3669]. It was re-published in full and became the first adopted project whose mirror is verified on its own merits: 108 creates with zero 429s, original topology restored, `push --verify` exit 0 against the two mirror roots alone [rec: northern-willow-0469].
- **The sixth, and the first found by measuring an adoption's inputs rather than its outputs**: neural-whoop's import carried 189 nodes and dropped the graph's whole tag taxonomy — 22 tags across 188 of them, plus a 6-hop pointer chain — because the protocol had no tag concept, while the hosted backend had implemented the operation all along [rec: fresh-spire-9002]. **It is repaired in the field, not only in the tooling** [rec: early-mesa-8507]: 22 definitions and 486 assignments restored across 188 of 189 nodes, per-tag counts identical to the archive, `push --verify` 0 drift, the archive root still at revision 28, and a second `heal tags` finding nothing. That makes it the evidence that **an adoption is not write-once**.
- **A fourth adopter, and the first genuine stranger** [rec: lean-field-0101]. `hypergraph-labs` adopted at 0.0.8 with the CLI installed from PyPI and no path back into this source tree — the route the first three all had an escape hatch from. Two roots, six seeded components, check 0/0, and a frontier honest about what is unproven. It is also the first adopter whose own work is *running experiments on this protocol*, so its graph and this one describe one line of work from two sides.
- **A fifth surface is opening**: agents on fresh cloud boxes adopting from PyPI with no prior context, as one arm of a controlled comparison. Unlike the others this one has a **control group**, so it can measure whether the protocol helps rather than only whether it holds [rec: twilight-wood-1934].

## Negative knowledge

- [scope: mirroring an adopted project | confidence: high | evidence: northern-willow-0469] any node mirrored before its true parent existed on the mirror gets parented to the mirror root as a placeholder, and nothing later repairs it. On a3go this was two nodes, not just the epoch boundary the design anticipated. A topology audit — every local node's parent slugs mapped through `flywheel:` ids and compared against the mirror's `incoming_ids` — is what finds them; the epoch marker alone is not the whole set.

## Provenance

- patient-limit-9007 — Operator directive opening this gap
- vast-sky-3964 — dogfooding targets and adoption modes chosen; the acceptance bar defined
- humble-clover-7048 — a3go adopted, mode A
- stormy-dew-2969 — tbinn adopted, mode B
- careful-harbor-3902 — the manual-push deviation defect, caught by verify
- fond-tree-4727 — the acceptance loop held
- copper-moss-3669 — the stub-mirror defect measured on a3go and diagnosed
- northern-willow-0469 — a3go re-mirrored in full; the first mirror-only verify
- twilight-wood-1934 — the cloud-box adoption arm opened
- fresh-spire-9002 — the sixth field defect: a whole tag taxonomy dropped by an import with no word for it
- clear-moss-4527 — both directions built; the live repair still outstanding at that point
- early-mesa-8507 — neural-whoop's taxonomy recovered live; an adoption is not write-once
- lean-field-0101 — hypergraph-labs adopted from PyPI, the first adopter with no access to this checkout
- late-sage-5549 — re-homed under Dogfooding, which it was a peer of only by accident
