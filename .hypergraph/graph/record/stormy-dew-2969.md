---
node_id: b851f7cb-1cf6-55ec-9341-c1d4efeee2c3
slug: stormy-dew-2969
title: 'M6: tbinn adopted (mode B) — authored prehistory, epoch marker, honest five-component state graph, verified mirror'
created_at: '2026-08-07T20:55:23+00:00'
parents:
- humble-clover-7048
summary: 'Ground-up adoption proven on tbinn: three prehistory nodes from repo docs, epoch marker, state graph with a genuinely broken frontier node (the T metric), full mirror verified clean from plan bytes. Mode-B marker parentage defect found and fixed upstream.'
---
## What

Second field adoption (adoption thrust M6): ran hypergraph-adopt end-to-end on tbinn — mode B, the ground-up path. tbinn (TBINN: can a trained model lose parametric knowledge while keeping reasoning?) had two commits, disciplined narrative docs, and no graph; it now runs the protocol with a 5-record graph (root + three authored prehistory nodes + epoch marker), a five-component state graph, fresh AGENTS.md, and a verified full mirror.

## Why

bitter-sound-9744 names tbinn as the mode-B target (vast-sky-3964). The plan required re-inventory at execution time: the first clone showed only the pre-push stub; a re-fetch found the Operator's push landed (commit 4a6afe1, "Build and calibrate the Battery (B0–B6); first (K,R) frontier"), so adoption proceeded on the real work rather than a stub.

## Method

Mode B per the adopt skill: record root, then three Prehistory nodes distilled from the repo's own documents (Phase 0 program design; Battery build + validation 001; frontier experiment 002) — honest summaries with impacts, never event-by-event reconstruction; a doc-mining subagent brief cross-checked against PROGRESS.md/HYPOTHESES/PLAN/ARCHITECTURE/RELATED_WORK and both experiment RESULTS. Epoch marker parented on the newest prehistory node; `epoch.marker` in config. Five state components seeded with honest statuses: research-program (open — the subject-size decision), Battery K&R (working, with the floor/quarantine caveats), Battery T (broken — the first genuinely broken frontier node in any hypergraph deployment), intervention-frontier (open — beat the below-diagonal null), subjects-corpus (open). Eleven negative-knowledge entries carry the program's scars (retention-ratio floors, the Pythia thesis-confirming artifact, the quarantine:[] config trap, TinyStories prose-floor risk, kNN-LM/RAG dead end). Onboarding: fresh AGENTS.md with the sentinel block (no prior contract to reconcile). Mirror: entire graph pushed to fresh roots (11 nodes + legend), byte-identical from plan content; verify clean on a component-filtered union export.

## Result

`check` exits 0 on tbinn (5 record, 6 state nodes; 3 prehistory nodes epoch-exempt though authored compliant); STATE.md's frontier correctly ranks the broken T node first, then the three open gaps (tbinn commits 160f796, 3f9b443). Protocol findings fed back upstream during this adoption: (1) the adopt skill's mode-B marker rule prescribed `--root`, which the CLI correctly refuses when a root exists — skill + SPEC fixed to parent mode-B markers on the newest prehistory node (commit 3bbde90); (2) verify-by-file works even when a small mirror export returns inline: fetching the union of two projects' mirrors forces the file path, and splitting by graph component lets each repo verify against its own subset. The M2 lesson held: all mirror content was pushed from plan-extracted bytes and verified clean on the first try — no manual-transcription drift this time. The user-interview step was again skipped (autonomous); noted in the marker for the Operator.

## Repo

- repo: https://github.com/theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 3bbde90b17539e15272a8b3bb51bf736dfec9e35

## State Impact

- target: morning-crane-7863 — M6 done: mode-B adoption proven on tbinn; milestone list advances to M7
- target: bitter-sound-9744 — second external adoption landed: tbinn checks 0/0, frontier led by a real broken node; mode B validated in the field; both dogfooding targets now live
- target: dry-wildflower-2260 — new claim: adopt skill mode-B marker parentage corrected from field use (parent = newest prehistory node; CLI refuses a second root)
