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
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from boxlab import provision, runner  # noqa: E402
from boxlab.arms import ARM_ORDER, compose_primer, get_arm  # noqa: E402
from boxlab.box_ctl import BoxController  # noqa: E402
from boxlab.config import LabConfig  # noqa: E402

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
    print(LabConfig.load().describe())
    return 0


def cmd_primer(args) -> int:
    text = compose_primer(get_arm(args.arm))
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out} ({len(text.split())} words)")
    else:
        sys.stdout.write(text)
    return 0


def _wait_for_finish(box_id: str, run_id: str, ctl: BoxController,
                     *, timeout_s: float, label: str) -> str:
    """Poll until the mission process exits or the bound elapses. Returns state."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        time.sleep(15.0)
        alive = runner.is_alive(box_id, box=ctl)
        elapsed = int(timeout_s - (deadline - time.monotonic()))
        if alive is False:
            print(f"  [{label}] finished after ~{elapsed}s")
            return "finished"
        last = runner.tail(box_id, run_id, lines=1, box=ctl).strip()
        print(f"  [{label}] {elapsed:>4}s alive={alive} {last[:110]}")
    return "timeout"


def _assistant_texts(log: str) -> list:
    """Pull assistant message text out of a stream-json log (tolerant)."""
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
    return out


def cmd_smoke(args) -> int:
    arm = get_arm(args.arm)
    config = LabConfig.load()
    config.require(arm.name)
    ctl = BoxController()

    print(f"== smoke test · arm {arm.label} ==")
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
    result = provision.apply(box_id, config, arm, box=ctl, force=args.force)
    if not result.ok:
        print("      FAILED:\n" + result.log[-3000:])
        return _teardown(ctl, box_id, args, code=1)
    print(f"      ok ({result.log.strip().splitlines()[-1][:60] if result.log else ''})")

    print("[4/6] launching mission 1 (write a file) …")
    ok, note = runner.launch(box_id, "smoke1", SMOKE_MISSION_1, arm, box=ctl)
    print(f"      {note}")
    if not ok:
        return _teardown(ctl, box_id, args, code=1)
    state = _wait_for_finish(box_id, "smoke1", ctl,
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
    killed = runner.kill_mission(box_id, box=ctl)
    print(f"      killed={killed}")
    ok, note = runner.launch(box_id, "smoke2", SMOKE_MISSION_2, arm, box=ctl)
    print(f"      {note}")
    _wait_for_finish(box_id, "smoke2", ctl, timeout_s=args.mission_timeout,
                     label="run2")
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


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="lab", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("creds", help="show resolved credentials + provenance"
                   ).set_defaults(func=cmd_creds)

    pp = sub.add_parser("primer", help="print an arm's composed CLAUDE.md")
    pp.add_argument("arm", choices=ARM_ORDER)
    pp.add_argument("-o", "--out")
    pp.set_defaults(func=cmd_primer)

    ps = sub.add_parser("smoke", help="live end-to-end proof on one box")
    ps.add_argument("--arm", choices=ARM_ORDER, default="hypergraph")
    ps.add_argument("--box", help="reuse an existing box id")
    ps.add_argument("--ttl", type=int, default=3600)
    ps.add_argument("--mission-timeout", type=float, default=420.0)
    ps.add_argument("--keep-box", action="store_true")
    ps.add_argument("--force", action="store_true",
                    help="re-provision even if the arm marker matches")
    ps.add_argument("--save-logs", help="directory to write the raw logs to")
    ps.set_defaults(func=cmd_smoke)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
