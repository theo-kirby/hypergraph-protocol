---
node_id: 60ea0268-7bbf-5106-8663-5f5e9a51fae6
slug: fair-field-3265
title: Harness hygiene
created_at: '2026-08-09T09:41:07+00:00'
parents:
- cool-king-8586
summary: ''
---
Status: working

## Current

- What this project has learned about **running fleets of autonomous agents against live accounts** — harness discipline, as distinct from the protocol it is used to test. It exists because the first nine-run benchmark's failures were not about memory systems at all: they were about a harness that let nine agents share a namespace, a credential and an unasserted provisioning step [rec: staid-field-2723].
- The lessons generalise past this benchmark. Any future experiment that spends money on agents in parallel inherits them, and `research/boxlab/preflight.py` is where they are enforced [rec: staid-field-2723].

## Negative knowledge

- [scope: multi-agent experiment harnesses | confidence: high | evidence: staid-field-2723] letting an agent name its own published artifact is a cross-contamination channel, not a convenience. Nine agents on one paper under one GitHub owner produced three identical repo names, two force-pushes over each other's work, and one `git reset --hard FETCH_HEAD` onto a sibling arm's tree which the agent then read. Any identifier that must be unique across runs has to be assigned by the harness, so the collision is unreachable rather than detected after the fact.
- [scope: provisioning autonomous agents | confidence: high | evidence: staid-field-2723] a provisioning sentinel that fires when the script reaches its last line asserts nothing. `set -e` catches a command that fails; it cannot catch one that succeeds at doing nothing. `BOXLAB_PROVISION_OK` printed on all three boxes whose CLI install had silently failed, and those runs produced numbers nobody could interpret. Every arm needs a post-provision assertion that its memory system actually works, run against the box that will do the work.
- [scope: harvesting agent transcripts | confidence: high | evidence: staid-field-2723] excluding a credentials file from a harvest does not contain credentials. The agent prints them into the transcript, which is the one artifact the harvest cannot drop — measured at 30 `cat ~/research/.env` calls across six of nine runs, because the primer handed them a push command containing `${GITHUB_TOKEN}`. Redaction has to happen in memory before the first write, and the instruction that made them read the file has to go.
- [scope: sharing one service account across experimental arms | confidence: high | evidence: staid-field-2723] a shared account is a shared memory. Three arm-B seeds on one Flywheel account could list, read and overwrite each other's nodes, and all three inherited 458 nodes from unrelated past projects — one spent seven `get_node` calls reading a football campaign from two months earlier. An arm's memory must be verified **empty** before its run starts, not merely present.

## Provenance

- staid-field-2723 — four lessons from nine autonomous agents on shared accounts, and the preflight gate that enforces them
