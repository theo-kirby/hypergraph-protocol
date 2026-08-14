---
node_id: 9e42cc2f-e913-5d19-a33f-340914331a20
slug: damp-basin-8974
title: Distribution
created_at: '2026-08-14T13:24:21+00:00'
parents:
- cool-king-8586
summary: Spec-first, a PyPI CLI package as the vehicle, this repo as reference implementation and never a template; publishing proven an allow-list; the goal restated as an autonomous-research substrate everywhere it is said.
flywheel:
  node_id: e6697aa9-2f7c-5b23-8ef4-abc687d15567
  slug: tight-resonance-0454
  revision: 1
  pushed_at: '2026-08-14T13:37:04+00:00'
  content_sha256: 90ddf2603b04d44d62f71327377a03ef52368651457588daff287ea0250dfa0d
  parents_sha256: a7a7d736bcfc7a886dc3bd4b6b138fcbabbc3a0bb49408b1c19e0413f4420ad9
  parents: []
---
Status: working

## Current

How the protocol reaches anyone who is not in this checkout. The shape was decided once and has held [rec: damp-mountain-8757]: **spec-first** (SPEC.md is the durable artifact), a **PyPI CLI package** as the vehicle — which also installs the skills into an adopter's repo — and this repo as reference implementation and self-dogfood exhibit, which adopters never clone or fork. A Claude Code plugin remains an optional secondary channel.

- **The name** is `hypergraph-protocol` on PyPI and on npm, the latter a placeholder pointing at PyPI under the `kirbyt` account [rec: damp-mountain-8757] [rec: lively-willow-7648]. Licensed MIT with PEP 639 metadata [rec: lively-willow-7648].
- **Publishing is an allow-list, not the repo**, and that is measured rather than assumed: the wheel is 40 files / 415 KB and the sdist 14 files, so `tests/`, `.hypergraph/`, `STATE.md` and `AGENTS.md` all ship nothing, and `tests/test_packaging.py` fails if any is added to either hatchling include list [rec: twilight-wood-1934].
- **The README front door had to be corrected to match this node.** Quickstart opened with `./install.sh`, which requires cloning this repo — the one thing this node has said since the shape was decided that adopters never do — while the real path appeared nowhere. There is now an `## Install` section with two labelled routes and a doc test asserting the install lines, because that is the claim that went stale [rec: patient-sail-0175].
- **What the project says it is changed everywhere it is said** [rec: clever-ledge-6588]. It was "a protocol for keeping research projects legible to fresh agents" — a description of the mechanism, not of the goal. It is now **a substrate for autonomous research and engineering**: the memory layer an agent needs to carry work across months and contexts without a human holding the thread, aimed at a structural failure rather than a capability one, because a chat log is not memory, a codebase records only what was kept, and a task list rots. The two halves are separated by maturity **in public**. README, SPEC, AGENTS.md, the CLI docstring, the package description and the shipped agents-block all carry it.

## Negative knowledge

- [scope: naming/distribution of this project | confidence: high | evidence: damp-mountain-8757] Bare `hypergraph` is taken on PyPI; `hg*` names read as Mercurial (its CLI is `hg`); clone/fork distribution rejected — the protocol is an overlay on adopters' repos, not a template.

## Provenance

- damp-mountain-8757 — publication shape and name decision
- lively-willow-7648 — MIT license + PEP 639 metadata; npm name claimed with a PyPI-pointing placeholder
- twilight-wood-1934 — the packaging boundary measured empirically rather than assumed
- patient-sail-0175 — README front door corrected to the PyPI path
- clever-ledge-6588 — the goal restated as an autonomous-research substrate, and the maturity split published
- late-sage-5549 — distribution split out so the shipped half stops flying an open flag
