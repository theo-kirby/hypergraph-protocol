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

from . import preflight, provision, redact, runner
from .arms import Arm, get_arm
from .box_ctl import BoxController
from .config import EXPERIMENT_SLUG, LabConfig
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
    experiment: str = EXPERIMENT_SLUG

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
    # Did this run write anything to its memory system *before* the cut? A
    # cold-start measurement over a run with nothing to recover measures nothing:
    # two of three arm-B seeds wrote nothing before the cut and were scored on
    # recovering it anyway. Runs where this is False are excluded from the
    # cold-start statistic and the exclusion count is reported (METRICS.md §2).
    had_prior_state: Optional[bool] = None
    prior_state_detail: str = ""
    preflight_ok: Optional[bool] = None
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
            "harvested": self.harvested,
            "had_prior_state": self.had_prior_state,
            "prior_state_detail": self.prior_state_detail,
            "preflight_ok": self.preflight_ok,
            "events": self.events,
        }


def load_mission() -> str:
    return MISSION_PATH.read_text(encoding="utf-8").strip()


def load_continuation() -> str:
    return CONTINUATION_PATH.read_text(encoding="utf-8").strip()


def _harvest(ctl: BoxController, box_id: str, dest: Path, result: RunResult,
             secrets: Optional[Dict[str, str]] = None) -> bool:
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

    Excluding those files is necessary and was never sufficient. On the nine-run
    benchmark, agents ran `cat ~/research/.env` thirty times, so the keys reached
    the archive anyway — through the transcripts, which are the one thing the
    harvest cannot drop. The archive is therefore **redacted in memory**, between
    the base64 decode and the first `write_bytes`. Redacting a file already on
    disk would be closing the door after the leak.

    Transport is base64 over ssh stdout: no second channel, no temporary
    credential, and it works on a box with no outbound access of its own.
    """
    dest.mkdir(parents=True, exist_ok=True)
    start, end = "__BOXLAB_TAR_START__", "__BOXLAB_TAR_END__"
    script = (
        f"echo {start}\n"
        "cd ~ && tar czf - "
        "--exclude=research/.env "
        "--exclude=research/.provisioned "
        "--exclude='.pi/agent/mcp.json' "
        "--exclude='*/node_modules' "
        "--exclude='*/__pycache__' "
        "--exclude='research/text8*' "
        # Agents create their own virtualenvs and build trees. Measured on the
        # nine-run harvest: archives reached 657 MB with these included, against
        # 28 MB on the pilot which happened not to make a venv. None of it is
        # evidence — it is reconstructible from the committed code.
        "--exclude='*/venv' "
        "--exclude='*/.venv' "
        "--exclude='*/build' "
        "--exclude='*.zip' "
        "research "
        "$([ -d .pi/agent/sessions ] && echo .pi/agent/sessions) "
        "$([ -d .claude/projects ] && echo .claude/projects) "
        "2>/dev/null | base64 -w0\n"
        f"echo\necho {end}\n"
    )
    try:
        rc, out = ctl.ssh_exec(box_id, script, timeout=900.0)
    except Exception as exc:
        result.log(f"harvest failed: {exc}")
        return False
    # Sentinel framing, not prefix-guessing. `ssh_exec` returns stdout followed
    # by stderr, so an ssh banner lands *after* the payload — stripping only the
    # front left trailing junk and base64 failed with "Incorrect padding",
    # discovered on the pilot run. Frame both ends and take what is between.
    if start not in out or end not in out:
        result.log(f"harvest framing lost (rc={rc}) — no archive written")
        return False
    blob = out.split(start, 1)[1].rsplit(end, 1)[0]
    blob = "".join(ch for ch in blob if ch not in " \t\r\n")
    if not blob:
        result.log(f"harvest produced nothing (rc={rc})")
        return False
    try:
        raw = base64.b64decode(blob)
    except Exception as exc:
        result.log(f"harvest decode failed: {exc}")
        return False

    cleaned, changed = redact.redact_archive(raw, secrets or {})
    if changed < 0:
        # The archive would not re-pack. Keeping it unredacted is the one thing
        # that must not happen silently, so it is dropped and said out loud —
        # the run is unmeasurable, which is recoverable; a leaked key is not.
        result.log("harvest UNREDACTABLE (archive would not re-pack) — discarded")
        return False
    if changed:
        result.log(f"redacted credentials in {changed} archived file(s)")
    try:
        (dest / "workspace.tar.gz").write_bytes(cleaned)
    except Exception as exc:
        result.log(f"harvest write failed: {exc}")
        return False
    return True


def _fetch_artifact(ctl: BoxController, box_id: str, remote: str, dest: Path,
                    secrets: Optional[Dict[str, str]] = None) -> bool:
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
    dest.write_text(redact.redact(body, secrets or {}), encoding="utf-8")
    return True


def _had_prior_state(ctl: BoxController, box_id: str, config: LabConfig,
                     arm: Arm, seed: Optional[int]) -> tuple:
    """Did this run commit anything to its memory system before the cut?

    Measured at the cut, on the box, per arm — because the cold-start measure is
    otherwise vacuous. On the nine-run benchmark only one of three arm-B seeds
    had written to Flywheel before the cut; the other two were scored on
    recovering state that never existed. The one that *did* have six prior nodes
    failed to find them and rebuilt the whole tree a second time, which is the
    finding — but it is only visible once the two vacuous runs stop diluting it.

    Returns `(had_state, detail)`. `had_state` is None when the probe itself
    failed: unknown is not the same as no, and must not be scored as either.
    """
    start, end = "__PRIOR_START__", "__PRIOR_END__"
    if arm.name == "flywheel":
        key = config.flywheel_key_for(arm.name, seed, allow_shared=True)
        total = preflight.flywheel_node_count(config.flywheel_api_url, key) if key else None
        if total is None:
            return None, "flywheel account unreadable at the cut"
        return total > 0, f"{total} node(s) in this run's Flywheel account"

    if arm.name == "hypergraph":
        # The seeded root does not count as the run's own work — a run that wrote
        # nothing still has one record node, because provisioning made it.
        script = (f"echo {start}\n"
                  "ls ~/research/.hypergraph/graph/record/*.md 2>/dev/null | wc -l\n"
                  f"echo {end}\n")
        floor = 1
        label = "record node(s) beyond the seeded root"
    else:
        script = (f"echo {start}\n"
                  "cd ~/research 2>/dev/null && git rev-list --count HEAD 2>/dev/null "
                  "|| echo 0\n"
                  f"echo {end}\n")
        floor = 0
        label = "commit(s) in ~/research"

    try:
        _, out = ctl.ssh_exec(box_id, script, timeout=90.0)
    except Exception as exc:
        return None, f"probe failed: {exc}"
    if start not in out or end not in out:
        return None, "probe framing lost"
    body = out.split(start, 1)[1].rsplit(end, 1)[0].strip()
    digits = "".join(ch for ch in body.splitlines()[0] if ch.isdigit()) if body else ""
    if not digits:
        return None, f"probe returned no count ({body[:60]!r})"
    count = int(digits)
    return count > floor, f"{max(0, count - floor)} {label}"


def _write_redacted(path: Path, text: str,
                    secrets: Optional[Dict[str, str]] = None) -> None:
    """Write a harness/provisioning log with credentials stripped.

    These logs are ssh stdout. Provisioning echoes progress, and an agent's own
    output lands in the phase logs — either can carry a key the run was handed.
    Every file this driver writes goes through here for the same reason the
    archive does: the disk write is the point of no return.
    """
    path.write_text(redact.redact(text or "", secrets or {}), encoding="utf-8")


def _run_one(spec: RunSpec, config: LabConfig, harness: Harness,
             *, duration_s: float, coldstart_frac: float, outdir: Path,
             guard: Optional[SpendGuard], ttl: int) -> RunResult:
    arm: Arm = get_arm(spec.arm)
    result = RunResult(spec=spec)
    ctl = BoxController()
    run_dir = outdir / spec.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    box_id = ""
    # Resolved once per run and threaded through every write. Includes this
    # run's own Flywheel key, which no other run holds.
    secrets = redact.secret_values(config.values)

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
        pr, pf = preflight.provision_and_check(
            box_id, config, arm.name, harness, seed=spec.seed,
            experiment=spec.experiment, box=ctl)
        _write_redacted(run_dir / "provision.log", pr.log, secrets)
        (run_dir / "preflight.json").write_text(
            json.dumps(pf.to_dict(), indent=2), encoding="utf-8")
        result.preflight_ok = pf.ok
        if not pr.ok:
            result.note = "provisioning failed"
            result.log(result.note + " (see provision.log)")
            return result
        # The assertion BOXLAB_PROVISION_OK was standing in for. It printed on
        # all three arm-B boxes whose Flywheel CLI had failed to install, and
        # those runs went on to produce numbers nobody could interpret. A box
        # that cannot run its arm costs a box; a box that runs it badly costs the
        # experiment.
        for check in pf.checks:
            result.log(check.render().strip())
        if not pf.ok:
            result.note = ("preflight failed: "
                           + "; ".join(c.name for c in pf.failures))
            result.log(result.note)
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

        # Measured BEFORE the kill, while the session's work is at its fullest.
        # This is the gate on whether this run's cold-start number means anything.
        result.had_prior_state, result.prior_state_detail = _had_prior_state(
            ctl, box_id, config, arm, spec.seed)
        result.log(f"prior state at the cut: {result.had_prior_state} "
                   f"({result.prior_state_detail})")

        result.log("cold-start cut: killing the session")
        runner.kill_mission(box_id, harness, box=ctl)
        result.coldstart_at = time.time()
        runner.fetch_log(box_id, f"{spec.run_id}-p1", box=ctl)
        _write_redacted(run_dir / "phase1.log",
                        runner.fetch_log(box_id, f"{spec.run_id}-p1", box=ctl),
                        secrets)

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
        _write_redacted(run_dir / "phase2.log",
                        runner.fetch_log(box_id, f"{spec.run_id}-p2", box=ctl),
                        secrets)

        # --- harvest BEFORE teardown: the box is the only copy ---------------
        # `vectors.txt` is ~68 MB of text (measured on the pilot). It travels
        # inside the tarball, which gzips it, rather than through a second
        # base64 text transfer of the raw file. Only the small JSON is pulled
        # separately, so a run's headline settings are readable without
        # unpacking anything.
        _, probe = ctl.ssh_exec(
            box_id,
            "test -s ~/research/artifacts/vectors.txt && echo HAVE_VECTORS\n",
            timeout=60.0)
        got_vectors = "HAVE_VECTORS" in probe
        _fetch_artifact(ctl, box_id, "~/research/artifacts/results.json",
                        run_dir / "results.json", secrets)
        result.harvested = _harvest(ctl, box_id, run_dir, result, secrets)
        # A run whose evidence did not come home is NOT complete. Saying so is
        # the difference between noticing at teardown and noticing at analysis,
        # by which point the box is gone — the pilot reported "complete" over a
        # failed harvest and that is how the bug nearly slipped through.
        result.ok = result.harvested
        notes = [] if result.harvested else ["HARVEST FAILED — evidence not retrieved"]
        if not got_vectors:
            notes.append("no vectors.txt produced")
        result.note = "complete" if not notes else "; ".join(notes)
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
                   budget_usd: Optional[float] = None,
                   experiment: str = EXPERIMENT_SLUG,
                   skip_preflight: bool = False,
                   allow_shared_flywheel: bool = False) -> Dict[str, RunResult]:
    """Run every (arm, seed) concurrently and return the results by run id."""
    harness = harness or get_harness()
    for arm in arms:
        config.require(arm, harness.auth_env)

    # Before a single box exists, and therefore before a single cent. Every
    # failure this catches — a shared Flywheel account, a repo name already
    # taken, a drifted primer — would have produced a completed run that could
    # not answer the question it was launched to answer.
    if not skip_preflight:
        outdir.mkdir(parents=True, exist_ok=True)
        report = preflight.run_preflight(
            config, arms=arms, seeds=seeds, harness=harness,
            experiment=experiment, allow_shared_flywheel=allow_shared_flywheel,
            baseline_path=outdir / "flywheel-baseline.json")
        print(report.render(), flush=True)
        if not report.ok:
            raise RuntimeError(
                "preflight failed — refusing to launch. Fix these and re-run:\n"
                + "\n".join(f"  - {c.name}: {c.detail}" for c in report.failures))

    guard = None
    if budget_usd is not None:
        key = config.get(harness.auth_env)
        if not key:
            raise RuntimeError(f"{harness.auth_env} required for the spend guard")
        guard = SpendGuard(key, budget_usd)
        print(guard.report(), flush=True)

    outdir.mkdir(parents=True, exist_ok=True)
    specs = [RunSpec(arm=a, seed=s, experiment=experiment)
             for s in seeds for a in arms]
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
