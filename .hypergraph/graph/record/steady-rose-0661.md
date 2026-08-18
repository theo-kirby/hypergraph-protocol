---
node_id: ad8dfd14-730d-57ff-b70d-4fe5e071cace
slug: steady-rose-0661
title: 'U9: drift sweep — the documents agree with the code'
created_at: '2026-08-18T12:18:02+00:00'
parents:
- weathered-badger-8682
summary: ''
flywheel:
  node_id: 21627932-5e4d-5a01-b737-b524555ef0c1
  slug: tiny-fog-4325
  revision: 0
  pushed_at: '2026-08-18T12:18:05+00:00'
  content_sha256: feb2f70a540b972d5c46cd7ec2f49fc142a730c8ed0d03140671b07edd5c2b81
  parents_sha256: f1c3ff07ce5568cef10e7a5da051e9e476393a8d156a233d563df4f4046a991c
  parents:
  - 09450167-a7bf-566b-ae06-d4852c7baed9
---
## What

U9 of the 0.1.0 gate: the drift sweep — ten pure-text corrections that make the documents agree with the code and with each other. No behavior changed.

## Why

The audit found the instructions contradicting the mechanism in load-bearing places: the reconcile skill taught wall-clock enumeration (the pre-0.0.5 rule I5 exists to forbid) in the one skill that must get I5 right; three documents gave three different counts of who passes `--reconcile`; the dispatch skill named the abandoned-lane failure while omitting the `close` verb that prevents it; `check --since` — the PR gate the Collaboration story leans on — appeared nowhere in SPEC; the heal→`upgrade --graph` contradiction spanned five files; and README stated "≤ ~6 tool calls" as fact while the frontier holds that claim open as unmeasured.

## Method

1. reconcile step 3: "record nodes not ancestors of any frontier tip (reachability, never wall clock)"; step 5 shows `high_water_mark: <tip>, <tip>` and points at `hwm --tips` (reachability semantics) with `--suggest` staying migration-only.
2. Writer count, stated identically in reconcile, init and SPEC I3: three — init and adopt once each at setup, reconcile ongoing. SPEC I3's stray "acquires leases" phrasing went with it.
3. dispatch: `harvest` → `close` (refuses unharvested; `--force` abandons, say so) in the lifecycle and the guardrail.
4. SPEC Invariants now names the structural checks and branch-mode I1; SPEC Tooling documents `check --since <ref>`; the record skill tells contributors to run it before the PR.
5. heal → `upgrade --graph` in docs/internal/mirror.md's Retroactive-repair section, local-adapter.md ×3, SPEC ×2, README ×2 — zero `heal` command spellings remain outside historical graph nodes.
6. v0.0.5 stragglers checked: only the intentional migration prose remains (SPEC's I5 history, `--suggest` help, reconcile's migration branch).
7. README hedges the tool-calls claim: "≤ ~6 in our own use — whether that beats plain git on real work is an open benchmark question."
8. README fixture list corrected: `self` → `epoch`.
9. adopt trap 3 rewritten to the true trap: `NEW <kebab-name>` never auto-resolves to the minted slug; `--slug` exists but `SLUG_RE` requires `word-word-####`, so `--slug sim-substrate` is refused by shape, not policy (verified against the parser and tests before rewriting).
10. The six identical "## The CLI" preambles are one sentence each; record's tagging essay trimmed to its operative lines.

## Result

340 tests passed, 2 skipped; `sync` 0 violations, 0 drift. Grep-verified: no "two places", no wall-clock enumeration wording, no unhedged tool-calls claim, no stale heal spellings.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 29850173667ba95ba8f588a14e13dcd941bb273a

## State Impact

- target: dry-wildflower-2260 — the skill drift the audit measured is closed: reconcile teaches reachability and the multi-tip mark, dispatch teaches close, the writer count is three everywhere, the CLI preambles are one sentence
- target: young-wave-9364 — SPEC's drift is closed: check --since documented in Tooling, enforced-set sentences corrected (structural checks + branch-mode I1), the heal contradiction resolved, no stale version headers
