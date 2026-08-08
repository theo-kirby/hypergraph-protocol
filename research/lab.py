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

# Long runs are watched through a redirected file, never a TTY, so Python's
# block buffering would hide all progress until the process exits.
print = functools.partial(print, flush=True)  # noqa: A001

sys.path.insert(0, str(Path(__file__).resolve().parent))

from boxlab import analyze, experiment, provision, runner, spend  # noqa: E402
from boxlab.arms import ARM_ORDER, compose_primer, get_arm  # noqa: E402
from boxlab.box_ctl import BoxController  # noqa: E402
from boxlab.config import LabConfig  # noqa: E402
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
    result = provision.apply(box_id, config, arm, harness, box=ctl,
                             force=args.force)
    if not result.ok:
        print("      FAILED:\n" + result.log[-3000:])
        return _teardown(ctl, box_id, args, code=1)
    print(f"      ok ({result.log.strip().splitlines()[-1][:60] if result.log else ''})")

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
        outdir=outdir, budget_usd=args.budget)

    print("\n== results ==")
    for rid in sorted(results):
        r = results[rid]
        print(f"  {rid:<20} {'ok ' if r.ok else 'FAIL'} {r.note}")
    return 0 if all(r.ok for r in results.values()) else 1


def cmd_analyze(args) -> int:
    """Turn harvested run directories into the numbers METRICS.md asks for."""
    root = Path(args.outdir)
    run_dirs = sorted(d for d in root.iterdir()
                      if d.is_dir() and (d / "run.json").exists())
    if not run_dirs:
        print(f"no harvested runs under {root}")
        return 1

    reports = []
    for run_dir in run_dirs:
        # The workspace arrives as a tarball; unpack once, next to it.
        tarball = run_dir / "workspace.tar.gz"
        unpacked = run_dir / "workspace"
        if tarball.exists() and not unpacked.exists():
            import tarfile
            unpacked.mkdir(parents=True, exist_ok=True)
            with tarfile.open(tarball) as tf:
                tf.extractall(unpacked, filter="data")
        report = analyze.analyse_run(unpacked if unpacked.exists() else run_dir)
        # Label by the run, not by the unpacked directory's name.
        report["run"] = run_dir.name
        report["arm"] = json.loads((run_dir / "run.json").read_text()).get("arm")
        reports.append(report)

    print(f"{'run':<18} {'arm':<11} {'turns':>6} {'tools':>6} {'cost$':>8} "
          f"{'cold-start s':>13}")
    for r in reports:
        cs = (r.get("cold_start") or {}).get("time_to_first_productive_s")
        print(f"{r['run']:<18} {str(r.get('arm')):<11} "
              f"{r['totals']['assistant_turns']:>6} "
              f"{r['totals']['tool_calls']:>6} "
              f"{r['totals']['cost_usd']:>8.3f} "
              f"{(f'{cs:.0f}' if cs is not None else '-'):>13}")

    out = root / "analysis.json"
    out.write_text(json.dumps(reports, indent=2), encoding="utf-8")
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

    ps = sub.add_parser("smoke", help="live end-to-end proof on one box")
    ps.add_argument("--arm", choices=ARM_ORDER, default="hypergraph")
    ps.add_argument("--harness", choices=sorted(HARNESSES), default=None)
    ps.add_argument("--box", help="reuse an existing box id")
    ps.add_argument("--ttl", type=int, default=3600)
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
    pr.add_argument("--yes", action="store_true")
    pr.set_defaults(func=cmd_run)

    pa = sub.add_parser("analyze", help="score harvested runs")
    pa.add_argument("--outdir", default="research/runs")
    pa.set_defaults(func=cmd_analyze)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
