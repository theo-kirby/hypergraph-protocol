---
node_id: c3e858c6-b1c3-51e2-8487-f66b7a1d67f5
slug: protocol-benchmark-4417
title: Protocol benchmark
created_at: '2026-08-08T17:21:41+00:00'
parents:
- cool-king-8586
summary: ''
---
Status: open

## Current

- **The gap this closes.** Everything to date shows the protocol works *mechanically* — `check` reports 0 violations on three repos, and a fresh agent completed the full loop with zero violations [rec: fond-tree-4727]. No evidence yet shows it makes agent work *better* than plain git. The announcement is the last publication gap, and an announcement with no evidence is a claim, so the Operator parked the release and opened this thrust instead [rec: southern-ridge-1802].
- **The design.** Three isolated agents implement the same paper — word2vec (Mikolov et al. 2013), skip-gram with negative sampling on text8 — on three identical Ascii Box VMs. Arm A has git only, arm B Flywheel, arm C the Hypergraph protocol. Three seeds per arm, nine runs; one run per arm is an anecdote [rec: southern-ridge-1802].
- **Capability is confirmed, and the target is reachable but not free.** In a 27-minute pilot the agent wrote a Cython extension and produced a complete 71,290-word `vectors.txt` scoring 19.36%, against a 20% *reproduced* band and a 24.16% literature reference. Runs are two hours rather than three, on Operator decision after the cost data [rec: northern-tree-5868].

### The first nine-run benchmark (2026-08-08) — evidence, and a harness that invalidated most of it

- **It completed and it cost almost nothing.** 9/9 launched, cut, harvested; 0 boxes leaked; **$2.18** against a $27–49 estimate. Wall-clock was the wrong basis: most of a run is CPU training with no model calls [rec: ancient-dew-4488].
- **The pre-registered verdict stands: NO DETECTABLE DIFFERENCE at n=3.** Fidelity scored by us — flywheel median 30.41% (25.78–31.43), hypergraph median 21.46% (12.65–32.43) — and the leading median's range overlaps. Cold start was likewise indistinguishable (38/81/43s) after a classifier fix. A null result ships as-is [rec: ancient-dew-4488].
- **…and the run was NOT a controlled experiment, so it can support nothing stronger than that.** A forensic pass over all nine transcripts, the GitHub account and the Flywheel account found four defect classes, each of which corrupts the comparison rather than merely losing a run [rec: staid-field-2723]:
  - **The arms reached each other.** The primer told nine agents on one paper under one GitHub owner to "pick a descriptive kebab-case name"; three picked `word2vec-skipgram-text8`. Two force-pushed over it — hypergraph-s3's published work is gone — and flywheel-s1 answered a rejected push with `git fetch && git reset --hard FETCH_HEAD`, replacing its tree with a hypergraph arm's repo, graph and STATE.md included, then reading it. Twice. All three arm-B seeds shared one Flywheel account holding **458 nodes from unrelated past projects** [rec: staid-field-2723].
  - **Two of three arms ran with a broken memory system.** `flywheel setup --mode mcp --yes` exits non-zero, so all three arm-B boxes had the HTTP MCP, no CLI and no contract doc, and spent their opening turns guessing tool names. Arm C had no scaffolding at all; hypergraph-s1 spent its entire second phase hand-rolling the protocol and never returned to training, scoring lowest in its arm [rec: staid-field-2723].
  - **Live keys leaked into git-tracked data** — because the primer handed agents a `git push https://x-access-token:${GITHUB_TOKEN}@…` line, and they ran `cat ~/research/.env` thirty times [rec: staid-field-2723].
  - **The fidelity measure sampled one instant** [rec: staid-field-2723].
- **The 0/3-vs-6/6 control pattern is a SAMPLING ARTIFACT, not a finding.** It was correctly flagged as post-hoc when first recorded [rec: ancient-dew-4488]; it is now known to be wrong. git-s1 reached **22.03%** and git-s2 **23.29%** mid-run and published both to GitHub, then overwrote the local `artifacts/vectors.txt` the measure sampled. `boxwheel/word2vec-cpu-baseline` still holds git-s2's vectors [rec: staid-field-2723].
- **Independent scoring is load-bearing, and that is measured.** On identical vectors the pilot agent claimed 21.47% where our evaluator measured 19.36%, because its evaluation silently discarded 10,234 of 19,544 questions (52%) against our 1,717 (9%) — almost the entire semantic subset, the hard one [rec: northern-tree-5868].

### The hardened harness — built, tested, not yet launched

- **Isolation is by construction, not by check.** Repository names are assigned by the harness from (experiment, arm, seed); `publish-repo` takes no argument and rejects any, never force-pushes, and refuses a repo whose committed `.boxlab-run` marker names another run. Flywheel keys resolve per run, and the shared fallback must be asked for [rec: staid-field-2723].
- **Both protocol arms now start level.** Arm B's CLI install is fixed and a failure is fatal; arm C's two roots and a valid config are seeded by provisioning, so both begin with an initialised, empty memory system. The skill layer is present or absent for **both** arms together, per harness — giving one a host-readable skill the other lacks would be a fresh confound in the protocol's favour [rec: staid-field-2723].
- **Nothing unredacted reaches disk.** `research/boxlab/redact.py` strips known values and secret *shapes*, in memory between the harvest's base64 decode and its first write; an archive that will not re-pack is discarded rather than written raw. Validated against the real leak: 46 findings across 18 transcripts, 0 residual. History was rewritten and an object-level scan of every blob now finds only the deliberately-fake test fixture [rec: staid-field-2723].
- **`research/boxlab/preflight.py` gates the launch**, in two layers: before any box exists (credentials, per-run Flywheel isolation and account emptiness, nine repos reserved and verified empty, the version pin, the primer invariants), and on the actual box after provisioning and before the mission. The second is the assertion `BOXLAB_PROVISION_OK` was standing in for — that sentinel printed on every broken box [rec: staid-field-2723].
- **The independent variable is still isolated by construction.** `primers/_core.md` is byte-identical for every arm; the three memory sections differ and are held within 15% by test — measured at 785/761/806 words, a 5.9% spread [rec: twilight-wood-1934] [rec: staid-field-2723].
- **The control is a real control**, taught commit-as-record, a running `NOTES.md`/`DECISIONS.md`/`DEAD-ENDS.md`, branch-per-alternative and log interrogation. If the protocol cannot beat competent git hygiene, that is the finding [rec: twilight-wood-1934].
- **Cold-start resilience costs nothing to measure, and that is proven rather than assumed.** Neither harness is passed a resume flag, so killing the session and relaunching leaves only the box's filesystem. Live on both harnesses, a relaunched session asked what it had just done answered `NO-PRIOR-SESSION` [rec: twilight-wood-1934] [rec: scarlet-orchard-8774].
- **Harness: pi (pi.dev) on OpenRouter, `deepseek/deepseek-v4-pro`, all nine concurrent** — Operator directive. The choice is about risk, not price: a subscription quota wall landing mid-run would truncate arms unevenly while the charts still rendered [rec: scarlet-orchard-8774].

### Measurement, re-pre-registered (METRICS.md rev-1, 2026-08-09)

Fixed **before** the second launch and with no access to its data, because the first run showed three of the original measures could be satisfied by a run that measured nothing [rec: staid-field-2723]:

- **Fidelity is two numbers.** `fidelity_final` (the teardown artifact, unchanged) and `fidelity_best_recoverable` — the best model the run can still *point to*, scored over every vector dump in the harvest and the published repo but restricted to candidates whose number the run's **own record cites** within 0.5pp. A better file the run never mentions is luck, not recovered knowledge. **The gap between them is itself a measure: how much proven work each memory system lost** [rec: staid-field-2723].
- **"Produced a usable model at all" is a pre-registered binary outcome**, so a 0/3-vs-6/6 pattern is a result if it recurs rather than something noticed afterwards [rec: staid-field-2723].
- **Cold start counts only runs with something to recover.** `had_prior_state` is probed on the box at the cut, before the kill; ineligible runs are excluded and the exclusions are always reported. Only one of three arm-B seeds had written to Flywheel before the first run's cut — and that one failed to find its six prior nodes and rebuilt the whole tree a second time, which is the finding the two vacuous runs were diluting [rec: staid-field-2723].
- **`MIN_N = 3` and the direction-aware overlap test are deliberately unchanged**, and now pinned by test. Both were correct [rec: staid-field-2723].

### Open

- **PARKED by Operator decision (2026-08-09), unblocked but deliberately not started.** The hardened harness is finished and verified; nothing spends until the Operator resumes [rec: sweet-wave-7885].
- **Keys rotated.** `OPENROUTER_API_KEY`, `GITHUB_TOKEN` and `FLYWHEEL_API_KEY` were rotated by the Operator; `BOX_API_KEY` was deleted outright, which costs nothing — `box_ctl` shells out to the `box` CLI, which carries its own auth, and the lab resolves that variable only to display it in `creds` [rec: sweet-wave-7885].
- **Three Flywheel accounts could not be created, so arm B runs on one — a DECLARED, ASYMMETRIC confound.** Arm B's seeds can list, read and overwrite each other's nodes; arms A and C keep full isolation, so a reader who discounts arm B entirely still has a valid A-vs-C comparison. Attribution survives where isolation did not: preflight captures the account's full node-id set before launch (verified live: 458 ids) and `had_prior_state` reads only nodes created after it. Opt-in via `--shared-flywheel`; without the flag a multi-seed arm-B launch still hard-fails. Declared in METRICS.md rev-1 [rec: sweet-wave-7885].
- **Preflight is 21/21** with `--shared-flywheel` against live GitHub and Flywheel, and 19/20 without it — failing only on the three per-run keys that do not exist [rec: sweet-wave-7885].
- **Named and not implemented**, for whoever resumes: a harness-seeded per-run root node in Flywheel and a per-run tag on every node the run creates. Both narrow attribution; neither restores isolation. Only separate accounts do that [rec: sweet-wave-7885].
- **OpenRouter's `usage` field** appeared not to move immediately after a live run, so the spend guard may be partially blind *during* a run and reliable only between runs [rec: scarlet-orchard-8774].
- **Under pi, both protocol arms run without their skills layer** — a narrower test than either packaged product offers, biasing against both [rec: scarlet-orchard-8774] [rec: staid-field-2723].
- The lab ships nothing: both hatchling targets are allow-lists, verified by building the artifacts, and `tests/test_packaging.py` fails if `research/` is ever added [rec: twilight-wood-1934].

## Negative knowledge

- [scope: comparing agent memory systems | confidence: high | evidence: twilight-wood-1934] a primer that bundles research discipline with one system's mechanics cannot be used as an experimental arm — handing it to one arm and nothing to another measures prompt quality, not the system. Arms must share a byte-identical core and differ only in a length-matched section.
- [scope: driving headless agent harnesses | confidence: high | evidence: scarlet-orchard-8774] an agent's run log is not its session record. pi's print mode wrote 82 bytes — the final answer only — for a whole run, while the turn/token/cost tree auto-saved elsewhere on disk; a harvest scoped to the workspace would have destroyed the evidence at teardown and surfaced the loss only at analysis.
- [scope: scoring agent-produced results | confidence: high | evidence: northern-tree-5868] an agent's self-reported score is not a score. Measured, not assumed: 21.47% claimed against 19.36% actual on identical vectors, because the agent's evaluator silently dropped 52% of the test set. Independent scoring is load-bearing, not fastidiousness.
- [scope: measuring artifacts an agent overwrites | confidence: high | evidence: staid-field-2723] scoring one file at one instant measures when you looked, not what the run achieved. Two control runs reached 22–23%, published it, then overwrote the sampled artifact — and the measure reported them as producing nothing. Any measure over a mutable artifact needs a second reading of what the run can still point to.
- [scope: comparing tools where one ships an init path and one does not | confidence: high | evidence: staid-field-2723] handing arm B a live empty account and arm C a bare directory does not compare the systems; it compares whether each ships setup. One arm C run spent its entire second phase standing the protocol up and never returned to the task. Every arm has to start from an initialised, empty memory system, or the setup cost is the measurement.

## Provenance

- southern-ridge-1802 — Operator directive: publication parked, three-arm benchmark opened; design, arms, measures, seeds
- twilight-wood-1934 — M1: boxlab from box-wheel, the split primer, METRICS.md, packaging answered, first live smoke pass
- scarlet-orchard-8774 — M2: pi/OpenRouter harness, experiment driver, spend guard; cold start proven on both harnesses
- northern-tree-5868 — pilot: capability confirmed, self-grading bias measured, three harness defects fixed
- ancient-dew-4488 — M5: nine runs complete, $2.18, null result at n=3; 0/3-vs-6/6 flagged as post-hoc
- staid-field-2723 — the first run reclassified as uncontrolled; harness hardened across isolation, provisioning, credentials and publishing; preflight gate added; METRICS.md re-pre-registered as rev-1
- sweet-wave-7885 — Operator decision: one Flywheel account for arm B declared as an asymmetric confound; keys rotated; relaunch parked
