---
node_id: 7ee4c94b-ad0d-5368-acbd-7719e8d947df
slug: weathered-badger-8682
title: 'U8: init installs the onboarding contract; the block gains sync gate + branch discipline'
created_at: '2026-08-18T12:14:43+00:00'
parents:
- mellow-birch-2818
summary: ''
flywheel:
  node_id: 09450167-a7bf-566b-ae06-d4852c7baed9
  slug: young-truth-5380
  revision: 0
  pushed_at: '2026-08-18T12:14:46+00:00'
  content_sha256: 375c917f694d4b87bcfa19a5ba90bf8567c6eb4ed6323a247185b51c83c481ba
  parents_sha256: c8c9c61304755aee668934624142cdfd165980ee809988f8b67a4b8ac89d199d
  parents:
  - 2932ee7f-0366-55bf-96a9-764fcd675c8d
---
## What

U8 of the 0.1.0 gate: `hypergraph-init` now installs the agent onboarding contract, and the contract itself gains the branch discipline as a fifth non-negotiable with `hypergraph sync` as the gate.

## Why

The audit found day-zero adopters got two graphs and zero instructions to the agents the protocol exists for: only adopt wrote the AGENTS.md block, and the shipped template still stated the pre-sync `export` + `check` gate. Blind tests #1/#2 established that repo-level agent onboarding is required *and* sufficient for a protocol-naive agent to record its work — so an init that skips it initializes memory nobody consults. The template also never stated the collaboration rule (record anywhere, reconcile only on the default branch), which SPEC carries but no arriving agent would see.

## Method

- `templates/agents-block.md`: non-negotiable 4's gate becomes `hypergraph sync` (export + STATE.md + check + publish in one exit code); new non-negotiable 5 states the branch discipline. The new digest is registered in `SHIPPED_BLOCK_DIGESTS` (old digests stay, so every previously shipped block remains refreshable); `test_shipped_block_digest_is_registered` held the change honest.
- init SKILL.md: new step 8 "Onboarding install" — idempotent sentinel append to AGENTS.md (replace, never double; never break a `CLAUDE.md` symlink), `.hypergraph/AGENTS.md`, `hypergraph skills install` + `git check-ignore` — compressed from adopt's version. Step 7 becomes the `sync` gate. The step-3/4 ordering waffle is resolved: record node #1 first (with `NEW <kebab-name>` impact lines and the never-auto-resolves caveat stated), then the skeleton citing its minted slug.
- No new CLI command: adopt's sentinel hand-append is the precedent, and `upgrade_onboarding` already owns refresh — a block init writes is a shipped digest, so `upgrade` recognizes and refreshes it.
- `skills/hypergraph-init/references/agents-block.md` symlink added; `skills/references.yml` updated in the same commit (the manifest pin forces this). SPEC's per-project-files bullet says "installed by init and adopt"; adopt counts five non-negotiables.

## Result

340 tests passed, 2 skipped (the digest and manifest pins both exercised); `sync` 0 violations, 0 drift. Every path into the protocol — init, adopt, upgrade — now delivers the same current contract.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 9bb34e8c37a8ec81389b51fc8d19eda51bd95b6a

## State Impact

- target: dry-wildflower-2260 — init gains the onboarding install step (sentinel append, .hypergraph/AGENTS.md, skills install + check-ignore) and the resolved record-first ordering; day-zero adopters now get the contract adopt always wrote
- target: fond-sail-3288 — the shipped agents-block states the sync gate and the branch discipline as non-negotiable 5; the 0.1.0 digest is registered so upgrade keeps refreshing clean blocks
