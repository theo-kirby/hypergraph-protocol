---
node_id: 467a1cd2-bf16-5441-b81f-394819e90e72
slug: lively-spring-9646
title: '0.1.0 readiness audit: three-lens review converts not-ready feeling into a measured defect list'
created_at: '2026-08-18T11:07:06+00:00'
parents:
- southern-ridge-1802
summary: ''
artifacts:
- .hypergraph/evidence/2026-08-18-release-readiness-audit.md
flywheel:
  node_id: 9083f871-21b1-500f-b44a-980d99519eba
  slug: aged-disk-2774
  revision: 1
  pushed_at: '2026-08-18T11:07:30+00:00'
  content_sha256: 27758e343cfdc346e3cd07f941795718093b816ce98a32b01309eb143282fa69
  parents_sha256: 3a2f6aaddf88e3f9d0a45704cdf04b946be418c8f31fc2349b43d1282d83c28f
  parents:
  - 60dad4c5-2fbe-569b-acec-07595b948638
  artifacts_sha256: 860f5aace8b6cf911349496ac217e22dc20925637cf245ad98668f07195db081
  artifacts:
  - path: .hypergraph/evidence/2026-08-18-release-readiness-audit.md
    sha256: 6995361944ba8a1241ee3ff9a87734d81a16517f4a10000d3929698cb4e3c399
    artifact_id: c068e6d6-64a1-50a7-8f74-b2d05a7601a5
    uploaded_at: '2026-08-18T11:07:29.491993+00:00'
---
## What

A full-repo readiness audit for the 0.1.0 release, run as three independent parallel reviews — conceptual layer (SPEC, README, backend/, templates), implementation layer (tools/, tests/, packaging), and skills layer — plus a frontier read. The question, from the Operator: is the repo ready to publish 0.1.0? The answer: not yet, and the gap is now enumerated with file:line evidence rather than felt.

## Why

The Operator parked 0.1.0 and the announcement together, pending evidence [rec: southern-ridge-1802], and asked today whether the repo is "there yet". Feeling not-ready is not a gate; a measured defect list is. This audit converts the feeling into one.

## Method

Three reviewers, each blind to the others, each instructed to cite file:line for every claim and to verify by execution where possible. Verification that actually ran: the test suite (302 passed, 2 skipped, 11.52s); the fence-blind section parser and the slug-regex false positives reproduced live against synthetic nodes; the 0.0.11 wheel diffed sha256-identical to the working tree; the installed-skills payload measured from the wheel (347,970 bytes, 78% duplicated references); string-vs-parsed timestamp ordering divergence demonstrated on mixed `Z`/`+00:00` inputs. Tree at the commit named in `## Repo`. Full reports attached as the artifact.

## Result

The core holds: invariants I2/I4/I5/I6/I7 enforce, 302 tests pass, packaging is defended by tests that build real sdists, and the frontier honestly names the unproven half. Around that core, four defect clusters:

**Checker trust defects (all reproduced).** `split_sections` does not track code fences, so a fenced example `## State Impact` is read as a real declaration and duplicate headings merge silently — false violations and false passes on I2, in the tool whose product is trust; `claim_units` already has the correct fence logic in the same file. `SLUG_RE.findall` over free prose turns a URL like `.../repo-name-1234` into a hard I4 exit-1. Comment stripping is inconsistent: a leading HTML comment fails I6 and renders `[?]` in STATE.md. `check` against a missing export raises a bare traceback — the exact failure class `load_config`'s own docstring documents as having cost two benchmark runs. Five sites sort timestamps as strings, diverging on mixed `Z`/`+00:00`. `sync` and `hwm`, the two flagship composite verbs, have zero end-to-end tests.

**Skill/spec drift.** The reconcile skill states unreconciled enumeration by wall clock — the pre-0.0.5 rule I5 exists to forbid; the code is right, the instruction is wrong, in the one skill that must get I5 right. Three documents give three different counts of who passes `--reconcile` (the true answer is three: init, adopt, reconcile). The dispatch skill teaches open/ls/harvest and never mentions the close action, while naming the abandoned-lane failure it would remedy. `check --since` — the PR gate — appears nowhere in SPEC.md and nowhere in the record skill. The heal-vs-`upgrade --graph` contradiction spans five files. SPEC.md still heads its last section "v0.0.5". README states "~6 tool calls" as fact while the frontier holds that claim open as unmeasured.

**Distribution gaps.** `upgrade` skips skills not already installed, so no pre-0.0.11 adopter can ever receive hypergraph-dispatch from the documented upgrade path, and nothing tells them to re-run `skills install`. `hypergraph-init` writes no AGENTS contract at all — a day-zero adopter gets two graphs and zero instructions to the agents the protocol exists for; only adopt writes the block, and the shipped template still states the old export+check gate instead of `sync`. `install.sh` fails on its second run (the link guard fires on its own output). A repo stamped with the retracted 0.9.0 label gets permanent wrong "upgrade the CLI" advice. The installed skills payload is 348 KB, 78% of it six copies of spec.md and local-adapter.md.

**Weight without work.** mirror.md + flywheel.md are 802 lines — 34% of the conceptual layer, longer than SPEC.md — documenting the optional feature SPEC claims the protocol does not know exists. The adopt skill is 43% of all skill bytes, ships three representations of one procedure and a factual `--slug` error, and costs ~17k tokens on invoke. Dead: `tag_def`, `artifact_abspath`, the numpy dev-dependency, the viz signpost now two releases past its cut.

Missing entirely for an outside adopter: a CHANGELOG and versioning policy, a single CLI reference, a worked example with real nodes, a merge workflow that owns the multi-tip HWM, and any recovery path from a bad reconcile — the most likely destructive event in the protocol, whose remedy (rewinding the HWM) no document authorizes.

Full findings, per-file line counts, and all reproductions: see the attached evidence file.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 1a970296b1bb8fa29c7feddea9286eec9ab2b964

## State Impact

- target: wandering-sun-8831 — checker trust defects found and reproduced: fence-blind split_sections (false pass and false fail on I2), SLUG_RE prose false positives (URL becomes an I4 exit-1), inconsistent comment stripping on I6, load_graph bare traceback on missing export, string-sorted timestamps at five sites; sync and hwm have zero end-to-end tests
- target: dry-wildflower-2260 — skill drift measured: reconcile SKILL.md:43 states I5 enumeration by wall clock (the rule I5 forbids), dispatch SKILL omits the lane-closing action, three docs disagree on who passes --reconcile (true answer: three), adopt carries three representations of one procedure plus a factual --slug error at 43% of all skill bytes
- target: fond-sail-3288 — upgrade never installs a skill absent from the target, so pre-0.0.11 adopters can never receive hypergraph-dispatch via the documented path; installed skills payload measured at 348 KB, 78% duplicated references; install.sh fails on second run; 0.9.0-stamped repos get a permanent wrong upgrade loop
- target: young-wave-9364 — SPEC drift: check --since absent from SPEC while being the sold PR gate, I1 mechanically enforced in branch mode contra SPEC:63, heal vs upgrade --graph contradiction across five files, last SPEC section still headed v0.0.5, README states ~6 tool calls as fact while the frontier holds it unmeasured
- target: weathered-union-7494 — 0.1.0 gate candidates enumerated with evidence: checker fixes, init writing the agents-block, upgrade delivering new skills, drift sweep, CHANGELOG plus versioning policy, mirror docs off the public surface; the park decision now has a concrete exit checklist
