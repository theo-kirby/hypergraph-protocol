---
node_id: d51a3183-e750-5f46-bd85-9ad8e7c68fdb
slug: humble-clover-7048
title: 'M5: a3go adopted (mode A) — 108-node import, epoch, 8-component state graph, verified mirror'
created_at: '2026-08-07T20:41:51+00:00'
parents:
- late-isle-6483
- crisp-lake-4496
summary: 'First field adoption: a3go under the protocol end-to-end — union import (108 nodes), epoch marker, distilled state graph with honest frontier, contract reconciliation, fresh mirror roots verified clean. Protocol fix found: mirror_roots verify exemption.'
flywheel:
  node_id: b51b96f5-6287-55d3-b0e7-e8bf3763c813
  slug: shiny-mountain-4553
  revision: 1
  pushed_at: '2026-08-07T21:21:27+00:00'
  content_sha256: 7c8c61c06b4adf29c48e2cd50a628c8d2f104c1f3eefa2e7f26041647ec35c65
---
## What

First field adoption (adoption thrust M5): ran hypergraph-adopt end-to-end on a3go, the autonomous 3D-Go research campaign — mode A, with a 108-node pre-hypergraph Flywheel graph. a3go now runs the protocol: local backend, epoch marker `lively-orchard-3365`, an 8-component distilled state graph, rerouted AGENTS.md, and a verified one-way mirror under fresh roots.

## Why

bitter-sound-9744's acceptance bar: the protocol had only ever run on itself. a3go is the mode-A stress case chosen in vast-sky-3964 — a real external campaign with a legacy graph, docs that cite node-id prefixes, an index node declared "the system of record", and a Flywheel-native agent contract to reconcile.

## Method

Adopt skill step by step. Inventory: union export of both anchors (`purple-fog-6345` + `proud-king-2753`) in one call — 108 nodes, closure verified (0 missing parents), exceeding the 67 cited for the root alone. Import: 108 verbatim node files (ids/slugs preserved); config with mandatory `archive:` (artifacts stay on the frozen legacy graph). Epoch marker parented on the newest legacy node (`crimson-rice-4497`) per the full-import rule; `epoch.marker` in config. Distillation: four parallel subagent miners (repo docs; science-question branches; neural + phase-3 branches; the 41-descendant EXPANSION subtree), all ~25 doc-cited id-prefixes resolved to slugs against the export before writing provenance (b3ea0b95→rough-paper-7328 etc.). Eight state components seeded with honest statuses (6 working, 2 open) and 15 negative-knowledge entries with legacy evidence slugs. Onboarding: sentinel block appended, four Flywheel-native contract sections rerouted through hypergraph, CLAUDE.md→AGENTS.md symlink preserved, full `.hypergraph/AGENTS.md` written. Mirror: NEW record/state roots under this account (never pushing into the archive), 10 nodes + legend pushed byte-identical from plan content, `push --verify` clean against a 4-anchor union export.

## Result

`check` exits 0 on a3go: 0 violations, 0 warnings, 107 legacy record nodes epoch-exempt, HWM at the marker; STATE.md committed (a3go commits 9d078b2, 6bfd554). The frontier surfaces the real campaign gaps: strength-program open (S4 the 7³ decisive test never run, S5 unmet everywhere, 5³ just below parity) and staged-frontier open (29 staged directions, ARCH-1 keystone bottleneck). Distillation honesty preserved: the ko-ubiquity prior correction (98% claimed vs 18–32% measured), the n=32 parity artifact, and the overturned "cheap-tweak exhausted" meta-conclusion are all recorded as negative knowledge rather than silently smoothed. Two findings for the protocol itself: (1) verify flagged the fresh mirror record root as mirror-only drift — fixed by exempting config-declared `mirror_roots` (commit 3195a0b, 62 tests green); (2) the adopt skill's user-interview step cannot run autonomously — noted in the marker for the Operator. Limitation: PyPI 0.0.2 being unpublished, the adoption used the repo-path CLI (the M4 fallback).

## Repo

- repo: https://github.com/theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 3195a0bae4dc6d65cc3fe9dacb5e203caa408407

## State Impact

- target: morning-crane-7863 — M5 done: mode-A adoption proven on a3go; milestone list advances to M6
- target: bitter-sound-9744 — first external adoption landed: a3go checks 0/0 with 107 legacy nodes epoch-exempt, honest frontier, verified mirror; mode A validated in the field
- target: wandering-sun-8831 — new claim: push --verify exempts config-declared mirror_roots (gap found live on a3go); test count 62
