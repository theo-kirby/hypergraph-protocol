"""Refuse to launch a run that cannot produce a valid measurement.

The nine-run benchmark completed, harvested, and reported a defensible headline —
and was not a controlled experiment. Two of three arm-B boxes had no Flywheel CLI
because `flywheel setup --mode mcp --yes` exits non-zero without a skill flag.
Arm C had no `.hypergraph` at all. All three arm-B seeds shared one account
holding 458 nodes from unrelated projects. Three runs published to the same
repository and two force-pushed over it.

Every one of those is *observable before the mission starts*. None of them was
observed, because provisioning printed `BOXLAB_PROVISION_OK` whenever the script
reached the end — and it reached the end whether or not the arm's memory system
worked. `set -e` catches a command that fails. It cannot catch a command that
succeeds at doing nothing.

So the checks here are adversarial about the specific ways this run has already
gone wrong, and every one of them **fails the run** rather than warning. A
warning on a nine-box launch is a line of scrollback nobody reads until the
analysis does not make sense.

Two layers, at two moments:

- `run_preflight` — before a single box exists. Credentials, per-run Flywheel
  isolation and account emptiness, repository names created and verified empty,
  the version pin, the primer invariants. It costs nothing and it gates the whole
  launch.
- `check_box` — on the actual box, after provisioning, before the mission is
  launched. It is the assertion `BOXLAB_PROVISION_OK` was standing in for, and it
  runs against the box the run will actually use, not a representative one.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from . import provision
from .arms import ARM_ORDER, HYPERGRAPH_VERSION, compose_primer, get_arm
from .box_ctl import BoxController
from .config import (EXPERIMENT_SLUG, LabConfig, flywheel_key_var,
                     repo_name_for, run_id_for)
from .harness import Harness, get_harness
from .redact import secret_values

GITHUB_API = "https://api.github.com"

# Sentinels framing the on-box probe's output. ssh interleaves banners and
# stderr; taking what lies between two markers is the only reliable framing.
_BOX_START, _BOX_END = "__BOXLAB_PREFLIGHT_START__", "__BOXLAB_PREFLIGHT_END__"


@dataclass
class Check:
    """One assertion, its verdict, and enough detail to act on a failure."""

    name: str
    ok: bool
    detail: str = ""

    def render(self) -> str:
        mark = "ok  " if self.ok else "FAIL"
        return f"  [{mark}] {self.name}" + (f" — {self.detail}" if self.detail else "")


@dataclass
class Report:
    label: str
    checks: List[Check] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> Check:
        check = Check(name=name, ok=ok, detail=detail)
        self.checks.append(check)
        return check

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def failures(self) -> List[Check]:
        return [c for c in self.checks if not c.ok]

    def render(self) -> str:
        head = f"{self.label}: {'PASS' if self.ok else 'FAIL'} " \
               f"({len(self.checks) - len(self.failures)}/{len(self.checks)})"
        return "\n".join([head, *(c.render() for c in self.checks)])

    def to_dict(self) -> dict:
        return {"label": self.label, "ok": self.ok,
                "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail}
                           for c in self.checks]}


# ---- HTTP helpers (stdlib only — the lab has no request dependency) -----------

def _github(path: str, token: str, *, method: str = "GET",
            payload: Optional[dict] = None) -> tuple:
    """`(status, parsed_body)` from the GitHub API. Never raises on 4xx."""
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{GITHUB_API}{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json",
                 "User-Agent": "boxlab-preflight"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", "replace")
            return response.status, (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(body)
        except ValueError:
            return exc.code, {"message": body[:300]}
    except Exception as exc:  # DNS, TLS, timeout — indistinguishable to us
        return 0, {"message": str(exc)}


def flywheel_node_ids(api_url: str, key: str, *, page_size: int = 100,
                      max_pages: int = 40) -> Optional[List[str]]:
    """Every node id visible to `key`, or None if the account cannot be read.

    This is the **baseline** for a shared-account run. With one account across
    three seeds the arms are not isolated — they can list and read each other's
    nodes, and 458 unrelated nodes were already there — so isolation is
    impossible. What is still recoverable is *attribution*: an id captured before
    launch and absent after is not this experiment's, and every id that appears
    later belongs to the run window. That turns an uninterpretable measure into a
    weaker but honest one, and the confound is declared in METRICS.md rather than
    quietly absorbed.
    """
    ids: List[str] = []
    for page in range(1, max_pages + 1):
        payload = {"jsonrpc": "2.0", "id": page, "method": "tools/call",
                   "params": {"name": "flywheel_list_nodes",
                              "arguments": {"owners": ["me"], "page": page,
                                            "page_size": page_size}}}
        request = urllib.request.Request(
            api_url.rstrip("/") + "/mcp-server", data=json.dumps(payload).encode(),
            method="POST",
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json",
                     "Accept": "application/json, text/event-stream",
                     "User-Agent": "boxlab-preflight"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                envelope = json.loads(response.read().decode("utf-8", "replace"))
            body = json.loads(envelope["result"]["content"][0]["text"])
        except Exception:
            return None if not ids else ids
        ids.extend(str(n.get("node_id")) for n in body.get("nodes") or [])
        if not body.get("has_more"):
            break
    return ids


def flywheel_node_count(api_url: str, key: str) -> Optional[int]:
    """Total nodes visible to `key`, or None when the account cannot be read.

    None is not zero, and the caller must not treat it as such. An unreadable
    account is exactly as disqualifying as a full one: it means the run's memory
    system is not known to be its own.
    """
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "flywheel_list_nodes",
                          "arguments": {"owners": ["me"], "page": 1,
                                        "page_size": 1}}}
    request = urllib.request.Request(
        api_url.rstrip("/") + "/mcp-server", data=json.dumps(payload).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream",
                 "User-Agent": "boxlab-preflight"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            envelope = json.loads(response.read().decode("utf-8", "replace"))
        text = envelope["result"]["content"][0]["text"]
        return int(json.loads(text)["total"])
    except Exception:
        return None


# ---- pre-launch checks --------------------------------------------------------

def check_credentials(config: LabConfig, arms: List[str],
                      harness: Harness, report: Report) -> None:
    for arm in arms:
        missing = config.missing_for(arm, harness.auth_env)
        report.add(f"credentials · arm {arm}", not missing,
                   "" if not missing else "missing " + ", ".join(missing))


def check_primer_invariants(arms: List[str], report: Report) -> None:
    """The core must be byte-identical and no arm may see another's section.

    A drifted core would make the comparison measure prompt differences rather
    than memory systems, and it would do so invisibly: the run still completes
    and the charts still render.
    """
    composed = {arm: compose_primer(get_arm(arm)) for arm in arms}
    markers = {"git": "Your memory system: git and files",
               "flywheel": "Your memory system: Flywheel",
               "hypergraph": "Your memory system: the Hypergraph protocol"}
    from .arms import CORE_PRIMER
    core = CORE_PRIMER.read_text(encoding="utf-8").strip()
    missing_core = [a for a, text in composed.items() if core not in text]
    report.add("primer · shared core byte-identical across arms", not missing_core,
               "" if not missing_core else f"drifted for {missing_core}")

    leaked = []
    for arm, text in composed.items():
        for other, marker in markers.items():
            if other != arm and marker in text:
                leaked.append(f"{arm} sees {other}")
        if markers.get(arm) and markers[arm] not in text:
            leaked.append(f"{arm} has no memory section")
    report.add("primer · each arm sees only its own memory section", not leaked,
               "; ".join(leaked))

    counts = {a: len(get_arm(a).memory_primer().split()) for a in arms}
    spread = max(counts.values()) / min(counts.values()) if counts else 1.0
    report.add("primer · memory sections length-matched", spread <= 1.15,
               f"spread {spread:.3f} ({counts})")


def check_flywheel_isolation(config: LabConfig, seeds: List[int],
                             report: Report, *, allow_shared: bool = False,
                             baseline_path: Optional[Path] = None) -> None:
    """One account per arm-B seed, and every one of them empty.

    `allow_shared` is the Operator's explicit acceptance that this is not
    available — three Flywheel accounts could not be created (2026-08-09). It
    does not make the run isolated and does not pretend to: the arms can still
    list and read each other's nodes. What it does is capture the account's node
    ids **before** launch so every node created during the run is attributable,
    and register the confound as a passing-but-loud check so it appears in the
    report rather than in a footnote nobody reads.
    """
    if allow_shared and len(seeds) > 1:
        key = config.flywheel_key_for("flywheel", seeds[0], allow_shared=True)
        if not key:
            report.add("flywheel · shared account reachable", False,
                       "no FLYWHEEL_API_KEY at all")
            return
        ids = flywheel_node_ids(config.flywheel_api_url, key)
        if ids is None:
            report.add("flywheel · shared account reachable", False,
                       "account unreadable — a run against it is unattributable")
            return
        if baseline_path is not None:
            baseline_path.parent.mkdir(parents=True, exist_ok=True)
            baseline_path.write_text(json.dumps(
                {"captured_for_seeds": seeds, "node_ids": sorted(set(ids)),
                 "count": len(set(ids))}, indent=2), encoding="utf-8")
        report.add("flywheel · shared account baseline captured", True,
                   f"{len(set(ids))} pre-existing node(s) recorded"
                   + (f" → {baseline_path}" if baseline_path else "")
                   + "; nodes created after this point are the run's")
        report.add("flywheel · CONFOUND ACCEPTED (arms not isolated)", True,
                   f"seeds {seeds} share one account by Operator decision — they "
                   "can list and read each other's nodes. Declared in METRICS.md; "
                   "cross-arm contamination is NOT ruled out for arm B.")
        return

    problems = config.flywheel_isolation_problems("flywheel", seeds)
    if len(seeds) == 1 and problems:
        # A single run cannot contaminate a sibling. The shared key is allowed,
        # and said out loud so it is never mistaken for isolation.
        shared = config.flywheel_key_for("flywheel", seeds[0], allow_shared=True)
        report.add("flywheel · per-run key", bool(shared),
                   "single run: falling back to the shared FLYWHEEL_API_KEY"
                   if shared else "no key at all")
    else:
        report.add("flywheel · one distinct key per seed", not problems,
                   "; ".join(problems))
        if problems:
            return

    for seed in seeds:
        key = config.flywheel_key_for("flywheel", seed,
                                      allow_shared=(len(seeds) == 1))
        if not key:
            report.add(f"flywheel · account for seed {seed} is empty", False,
                       f"no key ({flywheel_key_var('flywheel', seed)})")
            continue
        total = flywheel_node_count(config.flywheel_api_url, key)
        if total is None:
            report.add(f"flywheel · account for seed {seed} is empty", False,
                       "account unreadable — cannot confirm it is this run's")
        else:
            report.add(f"flywheel · account for seed {seed} is empty", total == 0,
                       "" if total == 0 else
                       f"{total} pre-existing node(s); the run would orient on "
                       "someone else's graph")


def ensure_repos(config: LabConfig, arms: List[str], seeds: List[int],
                 report: Report, *, experiment: str = EXPERIMENT_SLUG,
                 create: bool = True) -> Dict[str, str]:
    """Create every run's repository up front; fail if a name is already taken.

    Creating them here rather than on first publish is what makes the collision
    *impossible* instead of merely unlikely: nine names are reserved before any
    agent runs, and a name that already holds someone's work stops the launch
    rather than being force-pushed over.
    """
    token, owner = config.github_token, config.github_owner
    names: Dict[str, str] = {}
    if not token or not owner:
        report.add("github · credentials", False,
                   "GITHUB_TOKEN and GITHUB_OWNER are required to reserve repos")
        return names

    for arm in arms:
        for seed in seeds:
            names[run_id_for(arm, seed)] = repo_name_for(arm, seed, experiment)
    duplicates = len(names) != len(set(names.values()))
    report.add("github · repo names unique per run", not duplicates,
               "" if not duplicates else f"collision in {sorted(names.values())}")
    if duplicates:
        return names

    for run_id, name in sorted(names.items()):
        status, body = _github(f"/repos/{owner}/{name}", token)
        if status == 404:
            if not create:
                report.add(f"github · {name}", True, "absent (not created: --no-create)")
                continue
            status, body = _github("/user/repos", token, method="POST", payload={
                "name": name, "private": False, "auto_init": False,
                "description": f"boxlab {run_id} — protocol benchmark"})
            report.add(f"github · {name} created", status == 201,
                       "" if status == 201 else
                       f"HTTP {status}: {body.get('message', '')}")
            continue
        if status != 200:
            report.add(f"github · {name}", False,
                       f"HTTP {status}: {body.get('message', '')}")
            continue
        # It exists. Empty is fine (a rerun of preflight); anything else is
        # someone's work, and this run must not be pointed at it.
        empty = bool(body.get("size", 0) == 0)
        report.add(f"github · {name} exists and is empty", empty,
                   "" if empty else
                   f"{body.get('size')} KB of existing content — pick a new "
                   "experiment slug or delete it deliberately")
    return names


def check_harness(config: LabConfig, harness: Harness, report: Report) -> None:
    report.add("harness · model pinned", bool(harness.default_model),
               harness.default_model or "no default model — a run would be "
                                        "unreproducible")
    report.add("harness · auth present", bool(config.get(harness.auth_env)),
               f"{harness.auth_env} " +
               ("resolved" if config.get(harness.auth_env) else "missing"))


def check_version_pin(report: Report) -> None:
    import re
    from pathlib import Path
    pyproject = (Path(__file__).resolve().parents[2] / "pyproject.toml"
                 ).read_text(encoding="utf-8")
    declared = re.search(r'^version = "([^"]+)"', pyproject, re.M)
    ok = bool(declared) and declared.group(1) == HYPERGRAPH_VERSION
    report.add("hypergraph · install pin matches pyproject", ok,
               f"pinned {HYPERGRAPH_VERSION}, pyproject "
               f"{declared.group(1) if declared else '?'}")


def run_preflight(config: LabConfig, *, arms: List[str], seeds: List[int],
                  harness: Optional[Harness] = None,
                  experiment: str = EXPERIMENT_SLUG,
                  create_repos: bool = True,
                  allow_shared_flywheel: bool = False,
                  baseline_path: Optional[Path] = None) -> Report:
    """Everything checkable before a box exists. Costs nothing; gates the launch."""
    harness = harness or get_harness()
    report = Report(label=f"preflight · arms {','.join(arms)} · seeds {seeds}")
    check_credentials(config, arms, harness, report)
    check_harness(config, harness, report)
    check_primer_invariants(arms, report)
    if "hypergraph" in arms:
        check_version_pin(report)
    if "flywheel" in arms:
        check_flywheel_isolation(config, seeds, report,
                                 allow_shared=allow_shared_flywheel,
                                 baseline_path=baseline_path)
    ensure_repos(config, arms, seeds, report, experiment=experiment,
                 create=create_repos)
    return report


# ---- on-box checks ------------------------------------------------------------

def _box_probe_script(arm_name: str, harness: Harness, secrets: List[str],
                      repo: str) -> str:
    """One bash probe emitting `key=value` lines between two sentinels.

    A single round trip, because nine boxes × one ssh call per assertion is slow
    enough that it would be tempting to skip — and a check that gets skipped is
    not a check.
    """
    # Grep for the literal secret values anywhere under ~/research except the two
    # files that are *supposed* to hold them. `.env` is chmod 600 by design; what
    # must not happen is a key landing in a note, a script, or a committed file.
    patterns = " ".join(f"-e {json.dumps(value)}" for value in secrets) or "-e __none__"
    arm_block = ""
    if arm_name == "flywheel":
        arm_block = """
echo "flywheel_cli=$(flywheel --version 2>&1 | head -1 | tr -d '\\n' || echo MISSING)"
"""
    elif arm_name == "hypergraph":
        arm_block = """
echo "hypergraph_cli=$(hypergraph --version 2>&1 | head -1 | tr -d '\\n' || echo MISSING)"
cd ~/research && hypergraph export >/dev/null 2>&1 \
  && hypergraph check --record .hypergraph/cache/record.json \
       --state .hypergraph/cache/state.json --config .hypergraph/config.yml \
       >/tmp/hgcheck.out 2>&1 \
  && echo "hypergraph_check=$(tail -1 /tmp/hgcheck.out | tr -d '\\n')" \
  || echo "hypergraph_check=FAILED $(tail -2 /tmp/hgcheck.out | tr -d '\\n')"
echo "hypergraph_roots=$(grep -c '_root:' ~/research/.hypergraph/config.yml 2>/dev/null || echo 0)"
"""
    else:
        arm_block = """
echo "git_state=$(cd ~/research && git status --porcelain 2>&1 | head -1 | tr -d '\\n' || echo NOREPO)"
"""

    return f"""
export PATH="$HOME/.local/bin:$HOME/.flywheel/bin:$PATH"
echo {_BOX_START}
echo "primer=$([ -f ~/research/RESEARCH_PRIMER.md ] && echo yes || echo no)"
echo "claudemd=$([ -f ~/research/CLAUDE.md ] && echo yes || echo no)"
echo "primer_sha=$(sha256sum ~/research/RESEARCH_PRIMER.md 2>/dev/null | cut -c1-16)"
echo "claudemd_sha=$(sha256sum ~/research/CLAUDE.md 2>/dev/null | cut -c1-16)"
echo "memory_marker=$(grep -c 'Your memory system' ~/research/CLAUDE.md 2>/dev/null || echo 0)"
echo "publish_helper=$([ -x ~/research/bin/publish-repo ] && echo yes || echo no)"
echo "publish_repo_name=$(grep '^BOXLAB_REPO_NAME=' ~/research/bin/publish-repo.conf 2>/dev/null | cut -d= -f2)"
echo "harness_cli=$({harness.cli_bin} --version 2>&1 | head -1 | tr -d '\\n' || echo MISSING)"
echo "git=$(git --version 2>&1 | head -1 | tr -d '\\n' || echo MISSING)"
echo "leaked_secret_files=$(grep -rIl -F {patterns} ~/research 2>/dev/null \
  | grep -v -e '^/root/research/.env$' -e '/research/.env$' -e '/research/.mcp.json$' \
  | head -5 | tr '\\n' ',')"
{arm_block}
echo {_BOX_END}
"""


def _parse_probe(out: str) -> Dict[str, str]:
    if _BOX_START not in out or _BOX_END not in out:
        return {}
    body = out.split(_BOX_START, 1)[1].rsplit(_BOX_END, 1)[0]
    parsed: Dict[str, str] = {}
    for line in body.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            parsed[key.strip()] = value.strip()
    return parsed


def check_box(box_id: str, config: LabConfig, arm_name: str,
              harness: Optional[Harness] = None, *, seed: Optional[int] = None,
              experiment: str = EXPERIMENT_SLUG,
              box: Optional[BoxController] = None) -> Report:
    """Assert a provisioned box can actually run its arm. Runs before the mission.

    This is the assertion `BOXLAB_PROVISION_OK` was standing in for. That sentinel
    printed whenever the script reached its last line, which it did on all three
    arm-B boxes whose Flywheel CLI had failed to install.
    """
    harness = harness or get_harness()
    ctl = box or BoxController()
    run_id = run_id_for(arm_name, seed)
    report = Report(label=f"box {box_id} · {run_id}")
    expected_repo = repo_name_for(arm_name, seed, experiment)
    secrets = sorted(secret_values(config.values).values())

    try:
        _, out = ctl.ssh_exec(
            box_id, _box_probe_script(arm_name, harness, secrets, expected_repo),
            timeout=180.0)
    except Exception as exc:
        report.add("box · reachable", False, str(exc))
        return report

    probe = _parse_probe(out)
    if not probe:
        report.add("box · probe framing", False,
                   "sentinels lost — cannot verify anything about this box")
        return report

    report.add("box · RESEARCH_PRIMER.md present", probe.get("primer") == "yes")
    report.add("box · CLAUDE.md present", probe.get("claudemd") == "yes")
    same = (probe.get("primer_sha")
            and probe.get("primer_sha") == probe.get("claudemd_sha"))
    report.add("box · primer and CLAUDE.md byte-identical", bool(same),
               "" if same else f"{probe.get('primer_sha')} vs {probe.get('claudemd_sha')}")
    # Exactly one memory section. Zero means the arm has no memory instructions;
    # more than one would mean an arm can see another's system.
    marker_count = probe.get("memory_marker", "0")
    report.add("box · exactly one memory section", marker_count == "1",
               f"found {marker_count}")

    report.add("box · publish-repo installed", probe.get("publish_helper") == "yes")
    report.add("box · repo assigned by the harness",
               probe.get("publish_repo_name") == expected_repo,
               f"conf says {probe.get('publish_repo_name')!r}, "
               f"expected {expected_repo!r}")

    leaked = [p for p in probe.get("leaked_secret_files", "").split(",") if p]
    report.add("box · no credential readable outside .env", not leaked,
               "" if not leaked else "found in " + ", ".join(leaked))

    cli = probe.get("harness_cli", "")
    report.add(f"box · {harness.cli_bin} runs", bool(cli) and "MISSING" not in cli, cli)
    report.add("box · git available", "MISSING" not in probe.get("git", "MISSING"),
               probe.get("git", ""))

    if arm_name == "flywheel":
        fw = probe.get("flywheel_cli", "")
        report.add("box · flywheel CLI runs", bool(fw) and "MISSING" not in fw,
                   fw or "not installed — this is the P1 failure, and it printed "
                         "BOXLAB_PROVISION_OK last time")
        key = config.flywheel_key_for(arm_name, seed, allow_shared=True)
        total = flywheel_node_count(config.flywheel_api_url, key) if key else None
        report.add("box · Flywheel account empty and reachable", total == 0,
                   "unreadable" if total is None else f"{total} node(s)")
    elif arm_name == "hypergraph":
        cli_line = probe.get("hypergraph_cli", "")
        report.add("box · hypergraph version matches the pin",
                   HYPERGRAPH_VERSION in cli_line, cli_line)
        check_line = probe.get("hypergraph_check", "")
        report.add("box · seeded graph passes check",
                   "0 violation(s)" in check_line, check_line)
        # Two `_root:` keys — a config that declares neither is the stub two arm-C
        # runs wrote to make `check` stop crashing.
        report.add("box · config declares both roots",
                   probe.get("hypergraph_roots") == "2",
                   f"{probe.get('hypergraph_roots')} root key(s) in config.yml")
    else:
        state = probe.get("git_state", "")
        report.add("box · git workspace clean", "fatal" not in state.lower(), state)

    return report


def provision_and_check(box_id: str, config: LabConfig, arm_name: str,
                        harness: Optional[Harness] = None, *,
                        seed: Optional[int] = None,
                        experiment: str = EXPERIMENT_SLUG,
                        box: Optional[BoxController] = None,
                        force: bool = False) -> tuple:
    """Provision, then assert it worked. Returns `(ProvisionResult, Report)`."""
    harness = harness or get_harness()
    arm = get_arm(arm_name)
    key = config.flywheel_key_for(arm_name, seed, allow_shared=True)
    result = provision.apply(box_id, config, arm, harness, box=box, force=force,
                             seed=seed, experiment=experiment, flywheel_key=key)
    if not result.ok:
        report = Report(label=f"box {box_id} · {run_id_for(arm_name, seed)}")
        report.add("box · provisioning script succeeded", False,
                   "see provision.log")
        return result, report
    return result, check_box(box_id, config, arm_name, harness, seed=seed,
                             experiment=experiment, box=box)
