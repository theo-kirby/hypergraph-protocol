---
node_id: 78963383-0279-58ce-b108-9ef4cbe42477
slug: mellow-birch-2818
title: 'U7: mirror docs off the public surface; SPEC Future work deleted; adopt collapsed'
created_at: '2026-08-18T12:10:38+00:00'
parents:
- old-jasper-8833
summary: ''
flywheel:
  node_id: 2932ee7f-0366-55bf-96a9-764fcd675c8d
  slug: proud-bush-5207
  revision: 0
  pushed_at: '2026-08-18T12:10:41+00:00'
  content_sha256: 85ff88668375813a219652a90bad4255c1fc5dc4fdc68db07724984d84e40cc0
  parents_sha256: c5bfde9053fbf2fc5929d300f879145a5fd275f1e8a801fcf5f8ecd1e370c888
  parents:
  - 2d1dd205-542e-5abf-9b63-6e18458129f4
---
## What

U7 of the 0.1.0 gate: the documentation weight cuts. The mirror's internals leave the agent-facing surface, SPEC's speculative Future-work list is gone, and the adopt skill is one procedure instead of three.

## Why

The audit measured mirror.md + flywheel.md at 802 lines — 34% of the conceptual layer, longer than SPEC.md — documenting the optional feature SPEC itself says the skills do not know exists. SPEC's Future-work list held speculative machinery whose durable items already live as frontier state nodes. The adopt skill was 43% of all skill bytes and shipped three representations of one procedure: a numbered workflow whose Mode A order was wrong, a §4 corrective note explaining why it was wrong, and a parallel "Mode A, end to end" walkthrough with the right order.

## Method

- `git mv backend/{mirror,flywheel}.md docs/internal/` (history preserved). All reference sites repointed — AGENTS.md, SPEC.md ×3, README.md (repo map now shows one `docs/internal/` line), both config comment blocks, backend/local-adapter.md ×5, backend/INTERFACE.md, tools/hypergraph.py ×5, tools/hypergraph_mirror.py ×5, one test docstring. The sdist no longer carries them (docs/ is not in the include list); the audit evidence file keeps its historical references unedited.
- SPEC "Future work (out of scope for v0.0.5)" deleted outright; the slot is refilled by U10's Versioning section.
- Adopt SKILL.md rewritten 363 → 286 lines: one mode-branched numbered workflow whose Mode A order is native (pull → import → `--init`, with the adopts-the-imported-root rule stated inline in one sentence); the corrective note and the duplicate walkthrough are gone; "The interview" and "Authoring nodes: four traps" kept verbatim (renumbered step pointers only); the stale `heal tags` reference became `upgrade --graph tags`; the HWM instruction now points at `hwm --tips`.

## Result

340 tests passed, 2 skipped; `sync` 0 violations, 0 drift. Conceptual-layer weight: the agent-facing doc set (SPEC, README, backend/{INTERFACE,local-adapter,lanes}, AGENTS.md) no longer contains any mirror-internals prose. Reconcile pass #2 follows this node.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 4bad0f2177af8909e09038697daaeb617be500eb

## State Impact

- target: empty-forest-6305 — mirror.md and flywheel.md now live in docs/internal/: CLI internals off the agent-facing surface, every pointer repointed, out of the sdist
- target: young-wave-9364 — SPEC's Future-work section is deleted (durable items already live on the frontier); the slot is reserved for the Versioning section
- target: dry-wildflower-2260 — adopt is one mode-branched procedure with the native Mode A order (363 to 286 lines); the interview and the four traps survive verbatim
