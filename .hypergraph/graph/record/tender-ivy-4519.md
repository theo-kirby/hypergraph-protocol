---
node_id: 1174c7a0-d939-5444-84f6-40835b0bb725
slug: tender-ivy-4519
title: 'Decision: orientation reads through the tail; reconcile triggers on pressure'
created_at: '2026-08-24T18:32:29+00:00'
parents:
- clever-ledge-6588
summary: ''
flywheel:
  node_id: 14bdd467-d5e1-55dc-9c11-095a4d7f7e03
  slug: hidden-block-2117
  revision: 0
  pushed_at: '2026-08-24T18:36:56+00:00'
  content_sha256: b86e94d813b29157da4820a2940df4b4065663ba9576f880f6ad99d2bb37c707
  parents_sha256: bad793a92b2edd19ca330cfa9de6a8962fd445ed61058d5ec51ce249e4789a24
  parents:
  - f0b33eb5-ae8b-50b2-9e40-f22b8eab7a46
---
## What

Operator decision: orientation reads *through* the state graph's high-water mark, and
reconcile triggers on measured pressure instead of operator discipline. The framing
that makes both principled: the state graph is a **checkpoint over the record log**,
and the unreconciled tail is a **replayable log** — every node past the HWM already
carries its declared impact (I2), so a reader can lay the tail's deltas over state
without writing anything. A stale HWM becomes compaction debt, not a correctness hole.

## Why

Field observation across the Operator's hypergraph repos: operator-guided sessions
record well but nobody runs reconcile, so the HWM drifts for weeks while sessions
keep orienting against the stale checkpoint — the exact staleness the state graph
exists to prevent, with the pending deltas sitting one command away the whole time.
The candidate remedies outside the protocol (operator discipline, nightly cron, repo
hooks) all fail the same way: they are external, calendar-shaped, and unavailable to
the autonomous mode the project leads with. This bears directly on the open research
question of whether orientation against distilled state actually works: unattended,
the answer was decaying toward "no" for a reason that is structural, not a capability
gap — which is why the fix belongs in the protocol.

## Method

Brainstorming session between the Operator and an agent, 2026-08-24. The reframe
(checkpoint + write-ahead log) fell out of noticing the protocol already has both
halves: the HWM enumerates the unreconciled tail exactly, and I2 guarantees every
tail node carries a machine-findable delta. Rejected alternatives, with reasons:
operator discipline (already observed failing); scheduled reconcile via hooks/cron
(external to the protocol, calendar-shaped when the real variable is tail size);
reconcile-after-every-record (kills the one-pass-per-batch coherence the
Collaboration section defends, and breaks on side branches where recording is safe
and reconciling is not).

## Result

Decided, three parts:

1. **Orient replays the tail.** Orientation = STATE.md + the declared impacts of
   every unreconciled node, laid on top, flagged pending-reconcile. Replayed deltas
   are the recording agents' claims, uncompacted and un-cross-checked — which is
   what makes reconcile still worth running, and what makes tail size the honest
   trigger variable.
2. **Reconcile triggers on pressure, on the default branch only.** Tail ≥ 3 at
   orientation on the default branch → the brief *leads* with "reconcile first,
   then the task". Tail 1–2 → note and replay. Session start is structurally the
   right trigger point: a fresh context is the librarian condition reconcile wants.
   The threshold is a skill-text constant, expected to move with dogfooding
   evidence.
3. **Worktrees and side branches never reconcile — first-class.** Parallel agents
   live in worktrees; they replay and note that the tail folds in on the default
   branch after merge. Reconcile pressure resolves at the merge points, which is
   where the coordinator (dispatch, cutting lanes from the default branch) stands.
   A side branch replays only the tail it can see — git's visibility model,
   accepted, with the ordinary remedy (merge the default branch in).

Two hazards named and accepted: replay quality degrades as the tail grows (that
degradation *is* the trigger), and two literal concurrent sessions on the default
branch could still both reconcile — advisory, same posture as lane claims, absorbed
by loud merge conflict on state files rather than corruption.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 9d46d5394ae0143dfa25a4b52e62b727b3c3a076

## State Impact

- target: soft-hill-6082 — new claim: staleness reframed — the state graph is a checkpoint, the unreconciled tail is its replayable log (I2 deltas), a stale HWM is compaction debt not a correctness hole; reconcile triggers on measured tail pressure (≥3 on the default branch at orientation), never calendar or operator discipline; worktrees/side branches never reconcile, they replay
- target: dry-wildflower-2260 — orient/reconcile/dispatch behavior decided: orient measures and replays the tail and leads with reconcile-first past the threshold; reconcile lists the pressure trigger as its standing cause; dispatch coordinators reconcile before cutting lanes
