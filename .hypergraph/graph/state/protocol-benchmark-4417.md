---
node_id: c3e858c6-b1c3-51e2-8487-f66b7a1d67f5
slug: protocol-benchmark-4417
title: Protocol benchmark
created_at: '2026-08-08T17:21:41+00:00'
parents:
- cool-king-8586
summary: 'Whether the protocol makes agent work better than plain git — still unmeasured, no longer parked. The rig is public in hypergraph-bench (labs archived): two arms, Claude Code harness, plain boxes; the mission decision and METRICS rev-2 gate the relaunch.'
flywheel:
  node_id: 756924b4-8adc-5bac-91a0-89158110daef
  slug: solitary-boat-7937
  revision: 4
  pushed_at: '2026-08-19T19:12:10+00:00'
  content_sha256: 910eff002cd893d2029fdbad4ea793c0c818f7496f230c6068af42218d1ee28c
  parents_sha256: a7a7d736bcfc7a886dc3bd4b6b138fcbabbc3a0bb49408b1c19e0413f4420ad9
  parents:
  - 9e687be1-1c80-56a2-bc0c-d4476edc0a2e
---
Status: open

## Current

**The gap this closes.** Everything to date shows the protocol works *mechanically* — `check` reports 0 violations on several repos, and a fresh agent completed the full loop with zero violations [rec: fond-tree-4727]. No evidence yet shows it makes agent work *better* than plain git. An announcement with no evidence is a claim, so the Operator parked the release and opened this thrust instead [rec: southern-ridge-1802].

- **The original design**: three isolated agents implement the same paper — word2vec skip-gram with negative sampling on text8 — on identical VMs. Arm A has git only, arm B Flywheel, arm C this protocol; three seeds per arm, nine runs, because one run per arm is an anecdote [rec: southern-ridge-1802]. **The control is a real control**, taught commit-as-record, a running `NOTES.md`/`DECISIONS.md`/`DEAD-ENDS.md`, branch-per-alternative and log interrogation — if the protocol cannot beat competent git hygiene, that is the finding [rec: twilight-wood-1934].
- **Capability is confirmed and the target is reachable**: a 27-minute pilot produced a complete 71,290-word `vectors.txt` scoring 19.36%, against a 20% reproduced band and a 24.16% literature reference [rec: northern-tree-5868].

### The first nine-run benchmark — evidence, and a harness that invalidated most of it

- **It completed and it cost almost nothing**: 9/9 launched, cut and harvested, 0 boxes leaked, **$2.18** against a $27–49 estimate [rec: ancient-dew-4488].
- **The pre-registered verdict stands: no detectable difference at n=3** — flywheel median 30.41%, hypergraph median 21.46%, ranges overlapping; cold start likewise indistinguishable. A null result ships as-is [rec: ancient-dew-4488].
- **…and the run was not a controlled experiment, so it can support nothing stronger.** A forensic pass over all nine transcripts and both accounts found four defect classes, each corrupting the comparison rather than merely losing a run [rec: staid-field-2723]: **the arms reached each other** (three agents picked the same repo name, two force-pushed over it, one answered a rejected push with `git reset --hard FETCH_HEAD` onto a sibling arm's tree and then read it — twice; all three arm-B seeds shared one account holding 458 unrelated nodes); **two of three arms ran with a broken memory system** (arm B's CLI install exits non-zero, arm C had no scaffolding at all and one seed spent its whole second phase hand-rolling the protocol); **live keys leaked into git-tracked data**; and **the fidelity measure sampled one instant**.
- **The 0/3-vs-6/6 control pattern is a sampling artifact, not a finding** — correctly flagged as post-hoc when first recorded [rec: ancient-dew-4488] and now known to be wrong: two control runs reached 22–23% mid-run and published it, then overwrote the local file the measure sampled [rec: staid-field-2723].
- **Independent scoring is load-bearing, and that is measured**: on identical vectors the pilot agent claimed 21.47% where our evaluator measured 19.36%, because its evaluation silently discarded 52% of the test set — almost the entire semantic subset [rec: northern-tree-5868].

### The hardened harness, and measurement re-pre-registered

- **Isolation is by construction, not by check** [rec: staid-field-2723]: repository names are assigned by the harness from (experiment, arm, seed), `publish-repo` takes no argument and never force-pushes, keys resolve per run, and **both protocol arms now start level** from an initialised, empty memory system — giving one a skill layer the other lacks would be a fresh confound in the protocol's favour. **Nothing unredacted reaches disk**: redaction strips known values and secret *shapes* in memory between the harvest's decode and its first write, validated against the real leak at 46 findings across 18 transcripts and 0 residual. `preflight.py` gates the launch in two layers, the second being the assertion the old provisioning sentinel was standing in for.
- **The independent variable is isolated by construction**: the primer core is byte-identical for every arm and the three memory sections are held within 15% by test, measured at a 5.9% spread [rec: twilight-wood-1934] [rec: staid-field-2723]. **Cold-start resilience costs nothing to measure** — neither harness is passed a resume flag, and a relaunched session asked what it had just done answers `NO-PRIOR-SESSION` [rec: twilight-wood-1934] [rec: scarlet-orchard-8774].
- **METRICS.md rev-1 was fixed before the second launch and with no access to its data**, because the first run showed three of the original measures could be satisfied by a run that measured nothing [rec: staid-field-2723]. Fidelity is now two numbers — the teardown artifact, and the best model the run can still *point to*, restricted to candidates whose number the run's own record cites — and **the gap between them is itself a measure: how much proven work each memory system lost**. "Produced a usable model at all" is a pre-registered binary outcome. Cold start counts only runs with something to recover. `MIN_N = 3` and the direction-aware overlap test are deliberately unchanged and now pinned by test.

### The rig's public home, and the second design

- **Unparked.** The rig lives in public `theo-kirby/hypergraph-bench`, protocol-run from its first commit; hypergraph-labs is archived with its run data, and its README points forward. Bench's own graph records the port (`patient-cove-7085` there) and the redesign (`dawn-prairie-5469` there); cross-repo provenance stays prose [rec: green-tower-8550].
- **The second design, decided and recorded before any spend**: **two arms** — A git control, C this protocol — with arm B (Flywheel) dropped; its code stays dormant and is never selected. That closes the wrong-account standing risk structurally (an account-identity gate covers even a revival) and retires the `--shared-flywheel` confound by construction. **Harness: Claude Code**, full product surface, so both remaining arms get their real packaged offering — removing the no-skills-layer bias pi imposed — billed by metered per-run Anthropic API keys so a quota wall cannot truncate arms unevenly [rec: green-tower-8550].
- **The chassis substrate is dropped entirely** — an accepted cost, recorded: the digest-pinned image constant stays behind in the archive, and the plain-box rig provisions by script again with version pins asserted by preflight [rec: green-tower-8550].
- **The launch is gated on deliberateness**: `EXPERIMENT_SLUG` is a sentinel preflight refuses, so the mission decision — walstore leading (hidden conformance ladder, a kill at every session boundary, deterministic score), perplexity and hillclimb as alternates — must land, with METRICS rev-2 pre-registered beside it, before anything can publish under a name [rec: green-tower-8550].

### Open

- **Before the gated live spike**: re-wire the counter acceptance smoke off the dropped chassis dispatcher onto the plain-box path; pin the `claude_code` model preflight requires; wire metered per-run keys through provisioning [rec: green-tower-8550].
- **The mission decision itself** — walstore vs alternates, METRICS rev-2, the real experiment slug — is its own future recorded decision, in bench's graph [rec: green-tower-8550].
- **The measured relaunch is still not run.** Nothing has spent money since the $2.18 first run [rec: green-tower-8550].

## Negative knowledge

- [scope: comparing agent memory systems | confidence: high | evidence: twilight-wood-1934] a primer that bundles research discipline with one system's mechanics cannot be used as an experimental arm — handing it to one arm and nothing to another measures prompt quality, not the system. Arms must share a byte-identical core and differ only in a length-matched section.
- [scope: scoring agent-produced results | confidence: high | evidence: northern-tree-5868] an agent's self-reported score is not a score. Measured, not assumed: 21.47% claimed against 19.36% actual on identical vectors, because the agent's evaluator silently dropped 52% of the test set. Independent scoring is load-bearing, not fastidiousness.
- [scope: measuring artifacts an agent overwrites | confidence: high | evidence: staid-field-2723] scoring one file at one instant measures when you looked, not what the run achieved. Two control runs reached 22–23%, published it, then overwrote the sampled artifact — and the measure reported them as producing nothing. Any measure over a mutable artifact needs a second reading of what the run can still point to.
- [scope: comparing tools where one ships an init path and one does not | confidence: high | evidence: staid-field-2723] handing arm B a live empty account and arm C a bare directory does not compare the systems; it compares whether each ships setup. One arm C run spent its entire second phase standing the protocol up and never returned to the task. Every arm has to start from an initialised, empty memory system, or the setup cost is the measurement.

## Provenance

- southern-ridge-1802 — Operator directive: publication parked, the three-arm benchmark opened
- twilight-wood-1934 — the lab, the split primer, METRICS.md, and the first live smoke pass
- scarlet-orchard-8774 — the pi/OpenRouter harness and spend guard; cold start proven on both harnesses
- northern-tree-5868 — the pilot: capability confirmed and self-grading bias measured
- ancient-dew-4488 — nine runs complete, $2.18, a null result at n=3
- staid-field-2723 — the first run reclassified as uncontrolled; the harness hardened and METRICS re-pre-registered
- sweet-wave-7885 — the shared-account confound declared; keys rotated; relaunch parked
- sweet-aspen-3667 — preflight proved readable but not writable; write probe added
- solemn-dawn-6752 — the standing wrong-account risk on arm B's provisioning, closed by the two-arm redesign
- lean-field-0101 — the lab split into hypergraph-labs; the environment became a digest-pinned image
- fond-tree-4727 — the mechanical-only evidence this thrust exists to go beyond
- green-tower-8550 — unparked: hypergraph-bench public, two arms, Claude Code, plain boxes, mission open
