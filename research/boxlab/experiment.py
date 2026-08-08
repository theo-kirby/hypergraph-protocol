"""The experiment driver: N seeds × 3 arms, in parallel, with the cold-start cut.

One run is one box, and its whole life is scripted here so that no arm can get a
different deal by accident:

    create → provision → launch(mission) → [half the budget] → kill →
    relaunch(continuation) → [budget ends] → kill → harvest → stop

Every timing decision is taken from a **single wall clock started per run**, not
from "when the previous step happened", so a slow provision on one box does not
silently give that arm a shorter working period than its siblings.

Three failure modes get explicit handling because each one would corrupt the
comparison rather than merely lose a run:

- **A leaked box burns credit silently.** Every path out of `_run_one` goes
  through `finally: stop`, and the box also carries a TTL as a backstop.
- **A mid-run budget kill would truncate one arm and bias the result.** The spend
  guard is therefore a *launch* gate only: it can refuse to start a run, never
  stop one.
- **Harvest before teardown, always.** The box is the only copy of the work until
  the archive is home.
"""

from __future__ import annotations

import base64
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from . import provision, runner
from .arms import Arm, get_arm
from .box_ctl import BoxController
from .config import LabConfig
from .harness import Harness, get_harness
from .spend import SpendGuard

PRIMERS_DIR = Path(__file__).resolve().parents[1] / "primers"
MISSION_PATH = PRIMERS_DIR / "mission.md"
CONTINUATION_PATH = PRIMERS_DIR / "continuation.md"

# Extra box lifetime beyond the mission budget, for provisioning and harvest.
TTL_SLACK_S = 2400

# How often the driver wakes to check a run's clock.
TICK_S = 30.0


@dataclass
class RunSpec:
    arm: str
    seed: int

    @property
    def run_id(self) -> str:
        return f"{self.arm}-s{self.seed}"


@dataclass
class RunResult:
    spec: RunSpec
    box_id: str = ""
    ok: bool = False
    note: str = ""
    phase1_launched_at: float = 0.0
    coldstart_at: float = 0.0
    ended_at: float = 0.0
    harvested: bool = False
    events: List[str] = field(default_factory=list)

    def log(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        line = f"[{stamp}] {self.spec.run_id}: {message}"
        self.events.append(line)
        print(line, flush=True)

    def to_dict(self) -> dict:
        return {
            "arm": self.spec.arm, "seed": self.spec.seed,
            "run_id": self.spec.run_id, "box_id": self.box_id,
            "ok": self.ok, "note": self.note,
            "phase1_launched_at": self.phase1_launched_at,
            "coldstart_at": self.coldstart_at, "ended_at": self.ended_at,
            "harvested": self.harvested, "events": self.events,
        }


def load_mission() -> str:
    return MISSION_PATH.read_text(encoding="utf-8").strip()


def load_continuation() -> str:
    return CONTINUATION_PATH.read_text(encoding="utf-8").strip()


def _harvest(ctl: BoxController, box_id: str, dest: Path,
             result: RunResult) -> bool:
    """Pull the workspace **and the harness session transcripts** home.

    `~/.pi/agent/sessions/` is not optional extra: pi's `-p` log holds only the
    final answer (82 bytes for a whole smoke run), while the session JSONL holds
    the turn-by-turn tree with tool calls, tokens and cost. Measures 2 and 3 are
    computed from it, so a harvest that skipped it would leave the run
    unmeasurable and nothing would say so until analysis.

    Two exclusions are security, not tidiness: `research/.env` holds live tokens,
    and `.pi/agent/mcp.json` holds the Flywheel bearer. They are dropped **at the
    source** rather than filtered later — an archive that briefly contains live
    credentials on a laptop is a leak that already happened.

    Transport is base64 over ssh stdout: no second channel, no temporary
    credential, and it works on a box with no outbound access of its own.
    """
    dest.mkdir(parents=True, exist_ok=True)
    script = (
        "cd ~ && tar czf - "
        "--exclude=research/.env "
        "--exclude=research/.provisioned "
        "--exclude='.pi/agent/mcp.json' "
        "--exclude='*/node_modules' "
        "--exclude='*/__pycache__' "
        "--exclude='research/text8*' "
        "research "
        "$([ -d .pi/agent/sessions ] && echo .pi/agent/sessions) "
        "$([ -d .claude/projects ] && echo .claude/projects) "
        "2>/dev/null | base64 -w0\n"
    )
    try:
        rc, out = ctl.ssh_exec(box_id, script, timeout=900.0)
    except Exception as exc:
        result.log(f"harvest failed: {exc}")
        return False
    blob = "".join(ch for ch in out if ch not in " \t\r\n")
    # Strip any ssh banner that leaked in front of the payload.
    while blob and not blob.startswith(("H4sI", "H4sJ")):
        blob = blob[1:]
    if not blob:
        result.log(f"harvest produced nothing (rc={rc})")
        return False
    try:
        (dest / "workspace.tar.gz").write_bytes(base64.b64decode(blob))
    except Exception as exc:
        result.log(f"harvest decode failed: {exc}")
        return False
    return True


def _fetch_artifact(ctl: BoxController, box_id: str, remote: str,
                    dest: Path) -> bool:
    """Pull one small text artifact, sentinel-framed against ssh noise."""
    start, end = "__ART_START__", "__ART_END__"
    try:
        _, out = ctl.ssh_exec(
            box_id, f"echo {start}\ncat {remote} 2>/dev/null || true\necho {end}\n",
            timeout=300.0)
    except Exception:
        return False
    if start not in out or end not in out:
        return False
    body = out.split(start, 1)[1].rsplit(end, 1)[0].lstrip("\n")
    if not body.strip():
        return False
    dest.write_text(body, encoding="utf-8")
    return True


def _run_one(spec: RunSpec, config: LabConfig, harness: Harness,
             *, duration_s: float, coldstart_frac: float, outdir: Path,
             guard: Optional[SpendGuard], ttl: int) -> RunResult:
    arm: Arm = get_arm(spec.arm)
    result = RunResult(spec=spec)
    ctl = BoxController()
    run_dir = outdir / spec.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    box_id = ""

    try:
        if guard is not None and guard.exceeded():
            result.note = "skipped: spend budget reached before launch"
            result.log(result.note)
            return result

        result.log("creating box")
        box_id = ctl.create(ttl=ttl).id
        result.box_id = box_id
        result.log(f"box {box_id}")

        if not ctl.await_ssh_ready(box_id):
            result.log("WARNING machine never answered ssh; continuing")

        result.log(f"provisioning arm={arm.name} harness={harness.name}")
        pr = provision.apply(box_id, config, arm, harness, box=ctl)
        (run_dir / "provision.log").write_text(pr.log, encoding="utf-8")
        if not pr.ok:
            result.note = "provisioning failed"
            result.log(result.note + " (see provision.log)")
            return result

        # The run's clock starts at the first launch, so every arm gets the same
        # working period regardless of how long its toolchain took to install.
        mission = load_mission()
        ok, note = runner.launch(box_id, f"{spec.run_id}-p1", mission, arm,
                                 harness, box=ctl)
        result.phase1_launched_at = time.time()
        result.log(f"phase 1 {note}")
        if not ok:
            result.note = f"launch failed: {note}"
            return result

        cut_at = result.phase1_launched_at + duration_s * coldstart_frac
        end_at = result.phase1_launched_at + duration_s

        # --- phase 1: work until the cold-start cut -------------------------
        while time.time() < cut_at:
            time.sleep(TICK_S)
            if runner.is_alive(box_id, harness, box=ctl) is False:
                result.log("phase 1 process exited early")
                break

        result.log("cold-start cut: killing the session")
        runner.kill_mission(box_id, harness, box=ctl)
        result.coldstart_at = time.time()
        runner.fetch_log(box_id, f"{spec.run_id}-p1", box=ctl)
        (run_dir / "phase1.log").write_text(
            runner.fetch_log(box_id, f"{spec.run_id}-p1", box=ctl),
            encoding="utf-8")

        # --- phase 2: a fresh session, same box, same disk -------------------
        ok, note = runner.launch(box_id, f"{spec.run_id}-p2", load_continuation(),
                                 arm, harness, box=ctl)
        result.log(f"phase 2 {note}")

        while time.time() < end_at:
            time.sleep(TICK_S)
            if runner.is_alive(box_id, harness, box=ctl) is False:
                result.log("phase 2 process exited early")
                break

        result.log("budget reached: stopping the session")
        runner.kill_mission(box_id, harness, box=ctl)
        result.ended_at = time.time()
        (run_dir / "phase2.log").write_text(
            runner.fetch_log(box_id, f"{spec.run_id}-p2", box=ctl),
            encoding="utf-8")

        # --- harvest BEFORE teardown: the box is the only copy ---------------
        got_vectors = _fetch_artifact(
            ctl, box_id, "~/research/artifacts/vectors.txt",
            run_dir / "vectors.txt")
        _fetch_artifact(ctl, box_id, "~/research/artifacts/results.json",
                        run_dir / "results.json")
        result.harvested = _harvest(ctl, box_id, run_dir, result)
        result.ok = True
        result.note = ("complete"
                       + ("" if got_vectors else " (no vectors.txt produced)"))
        result.log(result.note)
        return result

    except Exception as exc:  # a crashed driver must still free its box
        result.note = f"driver error: {exc}"
        result.log(result.note)
        return result
    finally:
        if box_id:
            try:
                ctl.stop(box_id)
                result.log(f"stopped box {box_id}")
            except Exception as exc:
                result.log(f"WARNING could not stop {box_id}: {exc}")
        (run_dir / "run.json").write_text(
            json.dumps(result.to_dict(), indent=2), encoding="utf-8")


def run_experiment(config: LabConfig, *, arms: List[str], seeds: List[int],
                   harness: Optional[Harness] = None,
                   duration_s: float = 3 * 3600,
                   coldstart_frac: float = 0.5,
                   outdir: Path = Path("research/runs"),
                   budget_usd: Optional[float] = None) -> Dict[str, RunResult]:
    """Run every (arm, seed) concurrently and return the results by run id."""
    harness = harness or get_harness()
    for arm in arms:
        config.require(arm, harness.auth_env)

    guard = None
    if budget_usd is not None:
        key = config.get(harness.auth_env)
        if not key:
            raise RuntimeError(f"{harness.auth_env} required for the spend guard")
        guard = SpendGuard(key, budget_usd)
        print(guard.report(), flush=True)

    outdir.mkdir(parents=True, exist_ok=True)
    specs = [RunSpec(arm=a, seed=s) for s in seeds for a in arms]
    ttl = int(duration_s + TTL_SLACK_S)
    results: Dict[str, RunResult] = {}
    threads = []

    def worker(spec: RunSpec) -> None:
        results[spec.run_id] = _run_one(
            spec, config, harness, duration_s=duration_s,
            coldstart_frac=coldstart_frac, outdir=outdir, guard=guard, ttl=ttl)

    for spec in specs:
        t = threading.Thread(target=worker, args=(spec,), name=spec.run_id)
        t.start()
        threads.append(t)
        time.sleep(8.0)  # Box caps box creation at 10/minute — stagger the starts
    for t in threads:
        t.join()

    summary = {rid: r.to_dict() for rid, r in results.items()}
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2),
                                         encoding="utf-8")
    if guard is not None:
        print(guard.report(), flush=True)
    return results
