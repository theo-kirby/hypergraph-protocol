---
node_id: c3e858c6-b1c3-51e2-8487-f66b7a1d67f5
slug: protocol-benchmark-4417
title: Protocol benchmark
created_at: '2026-08-08T17:21:41+00:00'
parents:
- cool-king-8586
summary: Whether the protocol makes agent work better than plain git — still unmeasured. Nine runs completed and were reclassified as uncontrolled; the harness is hardened, the measures re-pre-registered, and the relaunch is parked by the Operator.
flywheel:
  node_id: 756924b4-8adc-5bac-91a0-89158110daef
  slug: solitary-boat-7937
  revision: 3
  pushed_at: '2026-08-14T13:37:04+00:00'
  content_sha256: 0d04aba052ecdcfe08cfd1aca8f62a40072c9f7c753936e23a4f80fe12888450
  parents_sha256: a7a7d736bcfc7a886dc3bd4b6b138fcbabbc3a0bb49408b1c19e0413f4420ad9
  parents:
  - 9e687be1-1c80-56a2-bc0c-d4476edc0a2e
---
Status: open

## Current

**The gap this closes.** Everything to date shows the protocol works *mechanically* — `check` reports 0 violations on several repos, and a fresh agent completed the full loop with zero violations [rec: fond-tree-4727]. No evidence yet shows it makes agent work *better* than plain git. An announcement with no evidence is a claim, so the Operator parked the release and opened this thrust instead [rec: southern-ridge-1802].

- **The design**: three isolated agents implement the same paper — word2vec skip-gram with negative sampling on text8 — on identical VMs. Arm A has git only, arm B Flywheel, arm C this protocol; three seeds per arm, nine runs, because one run per arm is an anecdote [rec: southern-ridge-1802]. **The control is a real control**, taught commit-as-record, a running `NOTES.md`/`DECISIONS.md`/`DEAD-ENDS.md`, branch-per-alternative and log interrogation — if the protocol cannot beat competent git hygiene, that is the finding [rec: twilight-wood-1934].
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

### Open

- **Parked by Operator decision, unblocked but deliberately not started.** Nothing spends until the Operator resumes [rec: sweet-wave-7885].
- **Arm B runs on one Flywheel account — a declared, asymmetric confound.** Its seeds can read and overwrite each other; arms A and C keep full isolation, so a reader who discounts arm B entirely still has a valid A-vs-C comparison. Attribution survives where isolation did not: preflight captures the account's full node-id set before launch and `had_prior_state` reads only nodes created after it. Opt-in behind `--shared-flywheel`; declared in METRICS.md rev-1 [rec: sweet-wave-7885].
- **A standing risk**: the environment variable the lab reads for arm B's account points at an unrelated account, so a relaunch as configured today would provision arm B against the wrong one and the captured baseline belongs to that account. Parked, so nothing is broken now [rec: solemn-dawn-6752].
- **Under pi, both protocol arms run without their skills layer** — a narrower test than either packaged product offers, biasing against both [rec: scarlet-orchard-8774].
- **The lab has moved out into a private sibling repo** and `research/` is gone from this one; sibling repos rather than submodules, on an Operator decision, so labs consumes this package **from PyPI exactly as a stranger does** and every benchmark run is also a test of the published artifact [rec: lean-field-0101].
- **The provisioning-procedure defect class is closed at the root, not patched**: ~469 lines of bash are replaced by a container image built `FROM` a pinned base, with every run recording the chassis commit sha and both image ids — the environment is a recorded constant rather than a procedure nobody versioned. Proven live on three boxes, which found two more defects of the same class, both in the base image and both reported by the harness as exit 0 [rec: lean-field-0101].
- **The relaunch is still not run**, and choosing the mission, METRICS rev-2 and the second experiment are each their own decision [rec: lean-field-0101].

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
- solemn-dawn-6752 — the standing wrong-account risk on arm B's provisioning
- lean-field-0101 — the lab split into hypergraph-labs; the environment became a digest-pinned image
- fond-tree-4727 — the mechanical-only evidence this thrust exists to go beyond
