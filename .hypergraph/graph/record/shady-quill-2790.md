---
node_id: f637bf9e-befd-5024-b627-ef8b61122ec0
slug: shady-quill-2790
title: 'M1: adoption-epoch support in the checker (epoch.marker, I2 exemption for legacy history)'
created_at: '2026-08-07T20:06:24+00:00'
parents:
- vast-sky-3964
summary: 'epoch.marker config key: record nodes strictly older than the marker are I2-exempt (info count); unresolvable marker = violation; authoring never exempted. 4 new tests, 54 green; SPEC + config + adapter docs landed.'
---
## What

Built adoption-epoch support into the checker (adoption thrust M1): a config key `epoch: {marker: <record-slug>}` under which record nodes created strictly before the marker node's `created_at` are exempt from I2/template compliance, so imported legacy history checks clean without weakening the protocol for new work.

## Why

Mode-A adoption imports a legacy graph verbatim (vast-sky-3964); those nodes predate the templates, and strict I2 over them would produce a violation per legacy node — meaningless noise that would train agents to ignore the checker. The epoch draws the boundary at the "Adopted Hypergraph" decision node instead.

## Method

`resolve_epoch_cutoff` resolves `config["epoch"]["marker"]` in the record graph (unresolvable marker or unparseable `created_at` = I2 violation — a silently ignored epoch would re-flag every legacy node). `check_impacts` gains an optional `epoch_cutoff` param: nodes with `created < cutoff` are skipped and counted, one info finding reports the exempted count. `validate_node_content` deliberately does not thread the epoch through — authoring-time validation is never exempted. Split-mode parentage rule documented (marker is a parentless local root recording archive lineage in content, because the local backend rejects parent slugs that don't resolve locally; full-import mode parents the marker on the newest legacy node). New fixture `tools/fixtures/epoch/` (free-form legacy node + compliant marker) with four tests: legacy exempt under epoch config, same node violates without the config, post-epoch node without impacts still fails, unresolvable marker is a violation.

## Result

54/54 tests green (up from 50); `check` on this repo's own exports stays 0/0. Docs landed: SPEC I2 amendment + new "Adoption epochs" section under Conventions, `templates/config.example.yml` gains commented `epoch:` and `archive:` blocks, `backend/local-adapter.md` §Bootstrapping explains import-as-fork, the artifact limitation, and the split-mode `--root` marker. Commit 4e937f1.

## Repo

- repo: https://github.com/theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 4e937f12757ce28b7adfdf6bd17a709ce51ca3bc

## State Impact

- target: morning-crane-7863 — M1 done: epoch mechanism built and tested; milestone list advances to M2
- target: young-wave-9364 — new claim: SPEC gains the I2 adoption-epoch exemption and the Adoption epochs convention (marker, parentage rules, no-truncation)
- target: wandering-sun-8831 — new claim: checker supports epoch.marker (resolve_epoch_cutoff + check_impacts exemption); test count 54
