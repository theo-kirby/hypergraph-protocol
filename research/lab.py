#!/usr/bin/env python3
"""boxlab CLI — drive the protocol benchmark from the command line.

    uv run research/lab.py creds                  # what credentials resolved, and from where
    uv run research/lab.py primer <arm> [-o F]    # the exact CLAUDE.md an arm receives
    uv run research/lab.py smoke [--arm A]        # end-to-end proof on ONE throwaway box

`smoke` is the milestone that has to pass before nine boxes are worth spending on.
It proves the whole chain live — create, provision, launch detached under the
subscription token, the mission actually runs — and then tests the one mechanism
the experiment depends on and cannot assume: that killing the session and
relaunching gives a **genuine cold start**, with no memory of the previous
session beyond what is on disk.

It never publishes anything. The mission is trivial by design; the point is the
plumbing, not the research.
"""

from __future__ import annotations

import argparse
import functools
import json
import sys
import time
from pathlib import Path
from typing import Optional

# Long runs are watched through a redirected file, never a TTY, so Python's
# block buffering would hide all progress until the process exits.
print = functools.partial(print, flush=True)  # noqa: A001

sys.path.insert(0, str(Path(__file__).resolve().parent))

from boxlab import (analyze, experiment, preflight, report, runner,  # noqa: E402
                    spend)
from boxlab.arms import ARM_ORDER, compose_primer, get_arm  # noqa: E402
from boxlab.box_ctl import BoxController  # noqa: E402
from boxlab.config import EXPERIMENT_SLUG, LabConfig  # noqa: E402
from boxlab.harness import HARNESSES, get_harness  # noqa: E402

# The smoke mission writes one file and stops. No publishing, no network work —
# a smoke test that creates public GitHub repos is not a smoke test.
SMOKE_MISSION_1 = (
    "This is a plumbing smoke test, not research. Do exactly this and nothing "
    "more: write a file ~/research/artifacts/smoke.txt whose single line is "
    "SMOKE-OK followed by a space and the current UTC time. Then print the "
    "file's contents. Do NOT publish anything to GitHub, do NOT create any "
    "repository, and do NOT use any other tools."
)

# Probes session continuity. A genuine cold start cannot answer from memory.
SMOKE_MISSION_2 = (
    "Answer in one short sentence, from your conversation memory ALONE. Do not "
    "read any files, do not run any commands, do not use any tools. What file "
    "did you write earlier in this conversation? If you have no memory of any "
    "earlier turn in this conversation, reply with exactly: NO-PRIOR-SESSION"
)


def cmd_creds(args) -> int:
    config = LabConfig.load()
    harness = get_harness(getattr(args, "harness", None))
    print(config.describe(harness.auth_env))
    key = config.get("OPENROUTER_API_KEY")
    if key:
        print(spend.probe(key))
    return 0


def cmd_primer(args) -> int:
    text = compose_primer(get_arm(args.arm))
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out} ({len(text.split())} words)")
    else:
        sys.stdout.write(text)
    return 0


def _wait_for_finish(box_id: str, run_id: str, ctl: BoxController, harness,
                     *, timeout_s: float, label: str) -> str:
    """Poll until the mission process exits or the bound elapses. Returns state."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        time.sleep(15.0)
        alive = runner.is_alive(box_id, harness, box=ctl)
        elapsed = int(timeout_s - (deadline - time.monotonic()))
        if alive is False:
            print(f"  [{label}] finished after ~{elapsed}s")
            return "finished"
        last = runner.tail(box_id, run_id, lines=1, box=ctl).strip()
        print(f"  [{label}] {elapsed:>4}s alive={alive} {last[:110]}")
    return "timeout"


def _assistant_texts(log: str) -> list:
    """Pull assistant text out of a run log — stream-json or plain.

    Claude Code emits stream-json; pi emits its own (largely plain) format. The
    cold-start check must not depend on which, so this parses the structured form
    when it is there and falls back to the raw text, which is enough to spot a
    sentinel the harness printed verbatim.
    """
    out = []
    for line in log.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        message = obj.get("message")
        if not isinstance(message, dict):
            continue
        for block in message.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                text = (block.get("text") or "").strip()
                if text:
                    out.append(text)
    if not out and log.strip():
        out.append(log.strip()[-800:])  # plain-text harness: hand back the tail
    return out


def cmd_smoke(args) -> int:
    arm = get_arm(args.arm)
    harness = get_harness(args.harness)
    config = LabConfig.load()
    config.require(arm.name, harness.auth_env)
    ctl = BoxController()

    print(f"== smoke test · arm {arm.label} · harness {harness.name}"
          f"{' · ' + harness.default_model if harness.default_model else ''} ==")
    box_id = args.box
    if box_id:
        print(f"[1/6] reusing box {box_id}")
    else:
        print("[1/6] creating box …")
        box_id = ctl.create(ttl=args.ttl).id
        print(f"      box {box_id}")

    print("[2/6] waiting for ssh …")
    if not ctl.await_ssh_ready(box_id):
        print("      WARNING: machine never answered; continuing anyway")

    print(f"[3/6] provisioning for arm {arm.name} …")
    result, checks = preflight.provision_and_check(
        box_id, config, arm.name, harness, seed=args.seed, box=ctl,
        force=args.force)
    if not result.ok:
        print("      FAILED:\n" + result.log[-3000:])
        return _teardown(ctl, box_id, args, code=1)
    print(checks.render())
    if not checks.ok:
        print("      preflight FAILED on the live box — the guardrails are not "
              "holding, and a nine-box launch would repeat the last run's "
              "mistakes.")
        return _teardown(ctl, box_id, args, code=1)

    print("[4/6] launching mission 1 (write a file) …")
    ok, note = runner.launch(box_id, "smoke1", SMOKE_MISSION_1, arm, harness,
                             box=ctl)
    print(f"      {note}")
    if not ok:
        return _teardown(ctl, box_id, args, code=1)
    state = _wait_for_finish(box_id, "smoke1", ctl, harness,
                             timeout_s=args.mission_timeout, label="run1")
    log1 = runner.fetch_log(box_id, "smoke1", box=ctl)
    _, out = ctl.ssh_exec(
        box_id, "cat ~/research/artifacts/smoke.txt 2>/dev/null || echo MISSING\n",
        timeout=60.0)
    wrote_file = "SMOKE-OK" in out
    print(f"      mission state={state} · artifact written={wrote_file}")
    if not wrote_file:
        print("      --- log tail ---\n" + log1[-1500:])

    print("[5/6] cold-start probe: kill the session, relaunch, ask what it remembers …")
    killed = runner.kill_mission(box_id, harness, box=ctl)
    print(f"      killed={killed}")
    ok, note = runner.launch(box_id, "smoke2", SMOKE_MISSION_2, arm, harness,
                             box=ctl)
    print(f"      {note}")
    _wait_for_finish(box_id, "smoke2", ctl, harness,
                     timeout_s=args.mission_timeout, label="run2")
    log2 = runner.fetch_log(box_id, "smoke2", box=ctl)
    answers = _assistant_texts(log2)
    reply = " ".join(answers)[-400:] if answers else "(no assistant text captured)"
    cold = "NO-PRIOR-SESSION" in reply
    print(f"      reply: {reply.strip()[:200]}")
    print(f"      GENUINE COLD START: {cold}")

    if args.save_logs:
        d = Path(args.save_logs)
        d.mkdir(parents=True, exist_ok=True)
        (d / "smoke1.jsonl").write_text(log1, encoding="utf-8")
        (d / "smoke2.jsonl").write_text(log2, encoding="utf-8")
        print(f"      logs saved to {d}")

    print("[6/6] teardown")
    verdict = wrote_file and cold
    print(f"\n== SMOKE {'PASS' if verdict else 'FAIL'} == "
          f"(provision ok · mission ran={wrote_file} · cold start={cold})")
    return _teardown(ctl, box_id, args, code=0 if verdict else 1)


def _teardown(ctl: BoxController, box_id: str, args, *, code: int) -> int:
    if args.keep_box:
        print(f"      keeping box {box_id} (--keep-box)")
        return code
    try:
        ctl.stop(box_id)
        print(f"      stopped box {box_id}")
    except Exception as exc:  # a leaked box burns credit — say so loudly
        print(f"      WARNING: could not stop {box_id}: {exc}")
    return code


def cmd_preflight(args) -> int:
    """Everything checkable before a box exists — and it gates `run`.

    Nine boxes, three hours each, is a couple of hours of wall clock and a
    non-trivial API bill. The last nine-run launch produced a completed
    experiment that could not answer its question, for reasons every one of which
    was visible from a laptop beforehand: a shared Flywheel account, repo names
    that would collide, an arm whose CLI never installed.
    """
    harness = get_harness(args.harness)
    config = LabConfig.load()
    arms = list(args.arms)
    seeds = list(range(1, args.seeds + 1))
    result = preflight.run_preflight(
        config, arms=arms, seeds=seeds, harness=harness,
        experiment=args.experiment, create_repos=not args.no_create_repos)
    print(result.render())
    if args.out:
        Path(args.out).write_text(json.dumps(result.to_dict(), indent=2),
                                  encoding="utf-8")
        print(f"\nwrote {args.out}")
    if result.ok:
        print("\npreflight PASS — safe to launch.")
        return 0
    print("\npreflight FAIL — launching now would spend money on a run that "
          "cannot be interpreted. Fix the failures above.")
    return 1


def cmd_run(args) -> int:
    """The measured experiment: every arm, every seed, concurrently."""
    harness = get_harness(args.harness)
    config = LabConfig.load()
    arms = list(args.arms)
    seeds = list(range(1, args.seeds + 1))
    outdir = Path(args.outdir)

    total = len(arms) * len(seeds)
    hours = args.hours
    print(f"== protocol benchmark ==")
    print(f"  harness   {harness.name}"
          f"{' · ' + harness.default_model if harness.default_model else ''}")
    print(f"  arms      {', '.join(arms)}")
    print(f"  seeds     {seeds}")
    print(f"  runs      {total} boxes, {hours}h each, "
          f"cold-start cut at {hours * args.coldstart_frac:.2f}h")
    print(f"  budget    ${args.budget:.2f} (launch gate only — never kills a run)")
    print(f"  output    {outdir}")
    if not args.yes:
        reply = input("\nproceed? [y/N] ").strip().lower()
        if reply not in ("y", "yes"):
            print("aborted")
            return 1

    results = experiment.run_experiment(
        config, arms=arms, seeds=seeds, harness=harness,
        duration_s=hours * 3600, coldstart_frac=args.coldstart_frac,
        outdir=outdir, budget_usd=args.budget, experiment=args.experiment,
        skip_preflight=args.skip_preflight)

    print("\n== results ==")
    for rid in sorted(results):
        r = results[rid]
        print(f"  {rid:<20} {'ok ' if r.ok else 'FAIL'} {r.note}")
    return 0 if all(r.ok for r in results.values()) else 1


# What analysis actually reads. Extracting only these avoids unpacking hundreds
# of megabytes of agent-created virtualenv per run, and sidesteps the absolute
# symlinks inside those venvs, which Python's safe tar filter refuses outright
# (`AbsoluteLinkError` on research/venv/bin/python3 — hit on the real harvest).
EVIDENCE_SUFFIXES = (
    "artifacts/results.json",
    "NOTES.md", "DECISIONS.md", "DEAD-ENDS.md", "STATE.md", "README.md",
)
EVIDENCE_DIRS = (".pi/agent/sessions/", ".claude/projects/", ".hypergraph/")

# Every vector dump, not just the final artifact. `fidelity_best_recoverable`
# needs the candidates a run produced and then replaced — scoring only
# `artifacts/vectors.txt` is what made two control runs that reached 22–23% and
# published it read as "produced nothing".
EVIDENCE_STEMS = ("vectors",)


def _extract_evidence(tarball: Path, dest: Path) -> None:
    """Unpack only the files the measures read, skipping links entirely."""
    import tarfile
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball) as tf:
        for member in tf:
            # Symlinks are never evidence here, and an absolute one aborts the
            # whole extraction — skip them rather than filter them.
            if not member.isfile():
                continue
            name = member.name
            base = name.rsplit("/", 1)[-1]
            wanted = (any(name.endswith(s) for s in EVIDENCE_SUFFIXES)
                      or any(d in name for d in EVIDENCE_DIRS)
                      or any(base.startswith(s) for s in EVIDENCE_STEMS))
            if wanted:
                tf.extract(member, dest, filter="data")


@functools.lru_cache(maxsize=1)
def _analogy():
    """The frozen evaluator, loaded once. Never the arm's own score."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "analogy", Path(__file__).resolve().parent / "eval" / "analogy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _score_one(path: Path) -> Optional[dict]:
    """Score a single vector dump with OUR evaluator, or None if unreadable."""
    analogy = _analogy()
    try:
        index, matrix = analogy.load_vectors(path)
    except (SystemExit, ValueError, OSError, UnicodeDecodeError):
        return None
    result = analogy.evaluate(index, matrix, analogy.load_questions())
    result["bands"] = analogy.score_bands(result)
    result["source"] = str(path)
    return result


def _score_fidelity(workspace: Path) -> Optional[dict]:
    """`fidelity_final`: the artifact the run left behind at teardown."""
    matches = list(workspace.rglob("artifacts/vectors.txt"))
    return _score_one(matches[0]) if matches else None


def _score_best_recoverable(workspace: Path, run_dir: Path,
                            extra_records: Optional[list] = None) -> tuple:
    """`fidelity_best_recoverable`: the best model the run can still point to.

    Scores every vector dump reachable from the harvest and the published repo,
    then keeps only those whose number the run's own record cites (METRICS.md
    §1). A better file the run never mentions is not recovered knowledge — it is
    luck, and counting it would measure the harvest rather than the memory
    system.

    Returns `(best_entry_or_None, all_scored)`.
    """
    candidates = analyze.find_vector_candidates(workspace)
    scored = [entry for entry in (_score_one(p) for p in candidates) if entry]
    cited = analyze.cited_accuracies(
        analyze.record_text(workspace, extra=extra_records)
        + analyze.record_text(run_dir))
    return analyze.best_recoverable(scored, cited), scored


def _fetch_published(config: LabConfig, arm: str, seed: int, dest: Path,
                     experiment: str) -> Optional[Path]:
    """Download this run's published repo — the other place its results live.

    git-s2 reached 23.29%, pushed it, then overwrote the local artifact with a
    diverged run. `boxwheel/word2vec-cpu-baseline` still holds those vectors.
    A measure that never looks at the repo the run was told to publish to is not
    measuring what the run preserved.
    """
    import io
    import tarfile
    import urllib.request
    from boxlab.config import repo_name_for
    token, owner = config.github_token, config.github_owner
    if not token or not owner:
        return None
    name = repo_name_for(arm, seed, experiment)
    url = f"https://api.github.com/repos/{owner}/{name}/tarball"
    request = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}", "User-Agent": "boxlab-analyze"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            blob = response.read()
    except Exception:
        return None
    dest.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(fileobj=io.BytesIO(blob)) as tf:
            for member in tf:
                if member.isfile():
                    tf.extract(member, dest, filter="data")
    except (tarfile.TarError, OSError):
        return None
    return dest


def cmd_analyze(args) -> int:
    """Turn harvested run directories into the numbers METRICS.md asks for."""
    root = Path(args.outdir)
    run_dirs = sorted(d for d in root.iterdir()
                      if d.is_dir() and (d / "run.json").exists())
    if not run_dirs:
        print(f"no harvested runs under {root}")
        return 1

    config = LabConfig.load() if args.fetch_published else None
    reports = []
    for run_dir in run_dirs:
        tarball = run_dir / "workspace.tar.gz"
        unpacked = run_dir / "workspace"
        if tarball.exists() and not unpacked.exists():
            _extract_evidence(tarball, unpacked)
        r = analyze.analyse_run(unpacked if unpacked.exists() else run_dir)
        r["run"] = run_dir.name
        meta = json.loads((run_dir / "run.json").read_text())
        r["arm"] = meta.get("arm")
        r["harvested"] = meta.get("harvested")
        # Recorded at the cut by the driver. Runs that wrote nothing to their
        # memory system before the cut are excluded from the cold-start
        # statistic — see METRICS.md §2.
        r["had_prior_state"] = meta.get("had_prior_state")
        r["prior_state_detail"] = meta.get("prior_state_detail")
        r["preflight_ok"] = meta.get("preflight_ok")

        if unpacked.exists():
            fidelity = _score_fidelity(unpacked)
            if fidelity:
                r["fidelity"] = fidelity

            extra = []
            if args.fetch_published and meta.get("arm") and meta.get("seed"):
                published = _fetch_published(
                    config, meta["arm"], meta["seed"],
                    run_dir / "published", args.experiment)
                if published:
                    extra = [p for p in published.rglob("*")
                             if p.is_file() and p.name in
                             ("README.md", "results.json", "NOTES.md")]
                    for path in analyze.find_vector_candidates(published):
                        extra.append(path.parent / "README.md")
            best, scored = _score_best_recoverable(
                unpacked, run_dir, extra_records=[p for p in extra if p.exists()])
            r["fidelity_candidates"] = [
                {"source": e.get("source"),
                 "accuracy": (e.get("total") or {}).get("accuracy"),
                 "diverged": e.get("diverged")} for e in scored]
            if best:
                r["fidelity_best_recoverable"] = best
            r["fidelity_gap"] = analyze.fidelity_gap(r.get("fidelity"), best)
        print(f"  scored {run_dir.name}", flush=True)
        reports.append(r)

    summary = report.by_arm(reports)
    print()
    print(report.render(summary))

    out = root / "analysis.json"
    out.write_text(json.dumps({"runs": reports, "by_arm": summary}, indent=2),
                   encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="lab", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("creds", help="show resolved credentials + provenance")
    pc.add_argument("--harness", choices=sorted(HARNESSES), default=None)
    pc.set_defaults(func=cmd_creds)

    pp = sub.add_parser("primer", help="print an arm's composed CLAUDE.md")
    pp.add_argument("arm", choices=ARM_ORDER)
    pp.add_argument("-o", "--out")
    pp.set_defaults(func=cmd_primer)

    pf = sub.add_parser("preflight",
                        help="assert a launch can produce a valid measurement")
    pf.add_argument("--arms", nargs="+", choices=ARM_ORDER, default=list(ARM_ORDER))
    pf.add_argument("--seeds", type=int, default=3, help="seeds per arm")
    pf.add_argument("--harness", choices=sorted(HARNESSES), default=None)
    pf.add_argument("--experiment", default=EXPERIMENT_SLUG)
    pf.add_argument("--no-create-repos", action="store_true",
                    help="check names without reserving them on GitHub")
    pf.add_argument("-o", "--out", help="write the report as JSON")
    pf.set_defaults(func=cmd_preflight)

    ps = sub.add_parser("smoke", help="live end-to-end proof on one box")
    ps.add_argument("--arm", choices=ARM_ORDER, default="hypergraph")
    ps.add_argument("--harness", choices=sorted(HARNESSES), default=None)
    ps.add_argument("--box", help="reuse an existing box id")
    ps.add_argument("--seed", type=int, default=None,
                    help="run as this seed (default: a dedicated 'smoke' repo)")
    ps.add_argument("--ttl", type=int, default=3600)
    ps.add_argument("--minutes", type=float, default=None,
                    help="per-mission budget in minutes (overrides --mission-timeout)")
    ps.add_argument("--mission-timeout", type=float, default=420.0)
    ps.add_argument("--keep-box", action="store_true")
    ps.add_argument("--force", action="store_true",
                    help="re-provision even if the arm marker matches")
    ps.add_argument("--save-logs", help="directory to write the raw logs to")
    ps.set_defaults(func=cmd_smoke)

    pr = sub.add_parser("run", help="the measured experiment (spends money)")
    pr.add_argument("--arms", nargs="+", choices=ARM_ORDER, default=list(ARM_ORDER))
    pr.add_argument("--seeds", type=int, default=3, help="seeds per arm")
    pr.add_argument("--hours", type=float, default=3.0)
    pr.add_argument("--coldstart-frac", type=float, default=0.5)
    pr.add_argument("--harness", choices=sorted(HARNESSES), default=None)
    pr.add_argument("--budget", type=float, default=40.0,
                    help="USD launch gate; running agents always finish")
    pr.add_argument("--outdir", default="research/runs")
    pr.add_argument("--experiment", default=EXPERIMENT_SLUG)
    pr.add_argument("--skip-preflight", action="store_true",
                    help="launch without the pre-launch gate (you should not)")
    pr.add_argument("--yes", action="store_true")
    pr.set_defaults(func=cmd_run)

    pa = sub.add_parser("analyze", help="score harvested runs")
    pa.add_argument("--outdir", default="research/runs")
    pa.add_argument("--experiment", default=EXPERIMENT_SLUG)
    pa.add_argument("--fetch-published", action="store_true",
                    help="also score vectors from each run's published repo "
                         "(needed for fidelity_best_recoverable)")
    pa.set_defaults(func=cmd_analyze)

    args = p.parse_args(argv)
    if getattr(args, "minutes", None):
        args.mission_timeout = args.minutes * 60.0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
