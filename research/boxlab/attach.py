"""Re-attach to runs whose driver died, and finish their schedule.

The driver holds the whole schedule in memory — cold-start cut, budget end,
harvest, teardown — so if it dies the boxes keep working (they are launched
`nohup setsid` and survive by design) but nothing ever cuts, harvests, or stops
them. This module rebuilds that schedule from facts that outlive the driver: the
box ids and the phase-1 launch times recorded in its log.

It exists because that happened: the first nine-box run's driver was killed ten
minutes in by a caller-side timeout, with all nine agents still working. The
agents' independence from the driver is what made recovery possible; the driver's
schedule living only in memory is what made recovery necessary.

Timing is reconstructed from each run's **own** phase-1 launch time, not from a
single clock, so the arms keep the same working period they were promised even
though the recovery starts at an arbitrary moment.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from . import provision, runner  # noqa: F401  (provision re-exported for callers)
from .arms import get_arm
from .box_ctl import BoxController
from .experiment import (RunResult, RunSpec, _fetch_artifact, _harvest,
                         load_continuation)
from .harness import Harness, get_harness

TICK_S = 30.0


@dataclass
class AttachSpec:
    """One in-flight run, as reconstructed from the dead driver's log."""

    run_id: str
    arm: str
    seed: int
    box_id: str
    phase1_launched_at: float  # epoch seconds


def parse_driver_log(path: Path, *, day_epoch: float) -> List[AttachSpec]:
    """Recover box ids and phase-1 launch times from a driver log.

    The log stamps `[HH:MM:SS]`, so the caller supplies the epoch of local
    midnight for that day; a run that straddles midnight needs the later day for
    the wrapped entries, which is why this returns what it parsed rather than
    guessing.
    """
    boxes: Dict[str, str] = {}
    launched: Dict[str, float] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 4 or not parts[0].startswith("["):
            continue
        stamp = parts[0].strip("[]")
        run_id = parts[1].rstrip(":")
        try:
            h, m, s = (int(x) for x in stamp.split(":"))
        except ValueError:
            continue
        when = day_epoch + h * 3600 + m * 60 + s
        if parts[2] == "box":
            boxes[run_id] = parts[3]
        elif "phase 1 launched" in line:
            launched.setdefault(run_id, when)

    specs = []
    for run_id, box_id in sorted(boxes.items()):
        if run_id not in launched:
            continue
        arm, _, seed = run_id.rpartition("-s")
        specs.append(AttachSpec(run_id=run_id, arm=arm,
                                seed=int(seed) if seed.isdigit() else 0,
                                box_id=box_id,
                                phase1_launched_at=launched[run_id]))
    return specs


def _finish_one(spec: AttachSpec, harness: Harness, *, duration_s: float,
                coldstart_frac: float, outdir: Path,
                skip_coldstart: bool) -> RunResult:
    arm = get_arm(spec.arm)
    result = RunResult(spec=RunSpec(arm=spec.arm, seed=spec.seed),
                       box_id=spec.box_id)
    result.phase1_launched_at = spec.phase1_launched_at
    ctl = BoxController()
    run_dir = outdir / spec.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    cut_at = spec.phase1_launched_at + duration_s * coldstart_frac
    end_at = spec.phase1_launched_at + duration_s

    try:
        if not skip_coldstart:
            while time.time() < cut_at:
                time.sleep(TICK_S)
                if runner.is_alive(spec.box_id, harness, box=ctl) is False:
                    result.log("phase 1 exited early")
                    break
            result.log("cold-start cut: killing the session")
            runner.kill_mission(spec.box_id, harness, box=ctl)
            result.coldstart_at = time.time()
            (run_dir / "phase1.log").write_text(
                runner.fetch_log(spec.box_id, f"{spec.run_id}-p1", box=ctl),
                encoding="utf-8")
            ok, note = runner.launch(spec.box_id, f"{spec.run_id}-p2",
                                     load_continuation(), arm, harness, box=ctl)
            result.log(f"phase 2 {note}")
        else:
            result.log("cold-start window already passed — skipping the cut")

        while time.time() < end_at:
            time.sleep(TICK_S)
            if runner.is_alive(spec.box_id, harness, box=ctl) is False:
                result.log("session exited early")
                break

        result.log("budget reached: stopping the session")
        runner.kill_mission(spec.box_id, harness, box=ctl)
        result.ended_at = time.time()
        (run_dir / "phase2.log").write_text(
            runner.fetch_log(spec.box_id, f"{spec.run_id}-p2", box=ctl),
            encoding="utf-8")

        _, probe = ctl.ssh_exec(
            spec.box_id,
            "test -s ~/research/artifacts/vectors.txt && echo HAVE_VECTORS\n",
            timeout=60.0)
        got_vectors = "HAVE_VECTORS" in probe
        _fetch_artifact(ctl, spec.box_id, "~/research/artifacts/results.json",
                        run_dir / "results.json")
        result.harvested = _harvest(ctl, spec.box_id, run_dir, result)
        result.ok = result.harvested
        notes = [] if result.harvested else ["HARVEST FAILED"]
        if not got_vectors:
            notes.append("no vectors.txt produced")
        result.note = "complete" if not notes else "; ".join(notes)
        result.log(result.note)
        return result
    except Exception as exc:
        result.note = f"attach error: {exc}"
        result.log(result.note)
        return result
    finally:
        try:
            ctl.stop(spec.box_id)
            result.log(f"stopped box {spec.box_id}")
        except Exception as exc:
            result.log(f"WARNING could not stop {spec.box_id}: {exc}")
        (run_dir / "run.json").write_text(
            json.dumps(result.to_dict(), indent=2), encoding="utf-8")


def finish_runs(specs: List[AttachSpec], *, harness: Optional[Harness] = None,
                duration_s: float = 2 * 3600, coldstart_frac: float = 0.5,
                outdir: Path = Path("research/runs/main")
                ) -> Dict[str, RunResult]:
    """Carry every in-flight run to teardown, each on its own original clock."""
    harness = harness or get_harness()
    outdir.mkdir(parents=True, exist_ok=True)
    results: Dict[str, RunResult] = {}
    threads = []
    now = time.time()

    for spec in specs:
        cut_at = spec.phase1_launched_at + duration_s * coldstart_frac
        # A cut fired well after its slot would give that arm a shorter second
        # phase than its siblings, which is worse than no cut at all: it would
        # look like a cold-start measurement and not be one.
        skip = now > cut_at + 300

        def worker(s=spec, sk=skip):
            results[s.run_id] = _finish_one(
                s, harness, duration_s=duration_s,
                coldstart_frac=coldstart_frac, outdir=outdir,
                skip_coldstart=sk)

        t = threading.Thread(target=worker, name=spec.run_id)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()

    (outdir / "summary.json").write_text(
        json.dumps({k: v.to_dict() for k, v in results.items()}, indent=2),
        encoding="utf-8")
    return results
