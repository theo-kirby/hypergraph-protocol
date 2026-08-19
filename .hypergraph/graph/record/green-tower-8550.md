---
node_id: f61b4641-83db-55ce-ac3b-b0a82450474a
slug: green-tower-8550
title: 'The benchmark unparked: hypergraph-bench is the rig''s public home'
created_at: '2026-08-19T19:10:23+00:00'
parents:
- lean-field-0101
summary: ''
flywheel:
  node_id: 2e8cd627-28bd-5f54-900f-0029642b09b2
  slug: old-base-0780
  revision: 0
  pushed_at: '2026-08-19T19:12:10+00:00'
  content_sha256: 48f6043601adf99be12d77f40cee68ccc862876632d953400d4e34babd64505d
  parents_sha256: b8b36363eb7fa9ed3ecc05546eeb6a8ff037db7b12463bdd2ea7feb1ff553bfc
  parents:
  - 6236dee4-14b2-53c5-a181-708519d10638
---
## What

Stood up `theo-kirby/hypergraph-bench` — public, protocol-run from its first
commit — as the benchmark rig's home, superseding the private hypergraph-labs,
which is now archived. Redesigned the experiment on the way: two arms, Claude
Code harness on metered per-run API keys, plain boxes, mission deliberately
open.

## Why

The benchmark is the open thrust that blocks the announcement, and its
relaunch was parked inside a private repo whose graph nobody outside could
read. Operator decisions this session: bench supersedes labs (harvests,
transcripts and secrets stay out of the public repo); the chassis substrate
is not used at all — runs go over the plain-box path E1 proved; arm B
(Flywheel) is dropped from the design, its code dormant in the tree; the
harness is Claude Code, full product surface, billed by metered per-run
Anthropic API keys so a quota wall cannot truncate arms unevenly; and the
mission is chosen later as its own recorded decision.

## Method

Nine commits in bench: hygiene rails, packaging (pin moved to 0.0.13,
pyproject its single home), the verbatim port of labs `0c4d6ac` minus the
chassis driver (`chassis.py`, `spike.py`, `infra/`, the chassis test and the
counter's dispatcher config stayed behind), mission content and primers
minus the w2v mission, a delta commit, identity files, day-zero
hypergraph-init at 0.0.13, and the first record-and-reconcile. The deltas:
`EXPERIMENT_SLUG` is a sentinel preflight refuses to launch with, so the
w2v namespace cannot be silently reused; any selected flywheel arm must
match a declared `FLYWHEEL_EXPECTED_ACCOUNT_ID` identity, closing the
wrong-account class structurally even for the dormant arm. Verified along
the way: every CLI call the arm-C seed script and box probe make is
unchanged 0.0.8 → 0.0.13; the `claude_code` harness path needed no
restoration (provision/runner/preflight are harness-generic); `redact.py`
already covers both `sk-ant-` shapes; and one latent labs defect surfaced —
`cli._analogy()` loaded the evaluator from a path that never existed.

Bench's graph: roots `dawn-badger-5788` / `lean-timber-6623`; record nodes
`rough-flint-4634` (init), `patient-cove-7085` (the port),
`dawn-prairie-5469` (the redesign decision); reconciled, `check` 0/0. The
record root's Prehistory cites this repo's `southern-ridge-1802` and
`protocol-benchmark-4417`, and labs' `light-raven-6945`, `even-mesa-6897`,
`brisk-bloom-0868`, as prose. Labs: final commit `1bf2eb9` points its README
forward, recorded there as `crisp-mountain-0695`, then archived via
`gh repo archive` (reversible).

## Result

The rig is public and green: 97 tests pass offline, `hypergraph check`
clean, `labs creds` resolves masked, and `labs preflight` fails loudly on
the provisional slug — which is the test. Dropping arm B closes
`solemn-dawn-6752` and retires the `--shared-flywheel` confound by
construction; moving to Claude Code removes the no-skills-layer bias the pi
harness imposed on both protocol arms. Two costs are accepted and recorded:
dropping chassis gives up the digest-pinned image constant (this thrust's
provisioning-defect closure stays behind in the archive; the plain-box rig
provisions by script again, with version pins asserted by preflight), and
the counter acceptance smoke must be re-wired off the chassis dispatcher
before the gated live spike can run. Mission open: walstore leads (hidden
conformance ladder, kill at every session boundary, deterministic score);
perplexity and hillclimb are alternates; METRICS rev-2 pre-registers with
the choice. Nothing has spent money.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: d0e6265c63b4895599a6897a2824f55e0b1cf0a7

## State Impact

- target: protocol-benchmark-4417 — unparked: the rig is public in hypergraph-bench (labs archived); arm B dropped — two arms, solemn-dawn-6752 closed structurally, the shared-flywheel confound retired by construction; harness → Claude Code on metered per-run keys; chassis dropped for plain boxes; mission open, walstore leading
