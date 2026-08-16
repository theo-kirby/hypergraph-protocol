"""`hypergraph dispatch`: the local lane provider (backend/lanes.md).

The tests that carry the argument are the boundary ones: the brief travels on
stdin and never argv, teardown refuses while unharvested, and with no agent
configured `open` stands down at exit 0 — provisioned lane in hand, manual steps
printed. Lane identity is minted, never named by the caller.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from graph_fixtures import LOCAL, hg, local_graph_copy


def run(*argv):
    return hg.main([str(a) for a in argv])


def lane_repo(tmp_path):
    """A throwaway git repo carrying the local-graph fixture as its graph."""
    repo = tmp_path / "repo"
    (repo / ".hypergraph").mkdir(parents=True)
    graph_dir = local_graph_copy(repo / ".hypergraph")   # → repo/.hypergraph/graph
    (repo / ".hypergraph" / "config.yml").write_text(
        f"project: t\ngraph_dir: .hypergraph/graph\n")
    (repo / ".gitignore").write_text(".hypergraph/lanes/\n")
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    for args in (["add", "-A"], ["-c", "user.email=t@e", "-c", "user.name=t",
                                 "commit", "-qm", "init"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True)
    return repo


def config_path(repo):
    return repo / ".hypergraph" / "config.yml"


def dispatch(repo, *argv):
    return run("dispatch", *argv, "--repo", repo,
               "--config", config_path(repo),
               "--graph-dir", repo / ".hypergraph" / "graph")


def open_lane(capsys, repo, *argv):
    capsys.readouterr()
    code = dispatch(repo, "open", *argv)
    out = capsys.readouterr().out
    slug = out.split("lane ", 1)[1].split(":", 1)[0]
    return code, slug, out


def lane_commit(repo, slug, name="work.txt"):
    lane_dir = repo / ".hypergraph" / "lanes" / slug
    (lane_dir / name).write_text("did a thing\n")
    subprocess.run(["git", "-C", str(lane_dir), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(lane_dir), "-c", "user.email=t@e",
                    "-c", "user.name=t", "commit", "-qm", "lane work"], check=True)
    return lane_dir


# ------------------------------------------------------------------ provisioning

def test_open_mints_unique_lanes_the_caller_never_names(tmp_path, capsys):
    repo = lane_repo(tmp_path)
    code1, slug1, _ = open_lane(capsys, repo)
    code2, slug2, _ = open_lane(capsys, repo)
    assert code1 == 0 and code2 == 0
    assert slug1 != slug2
    for slug in (slug1, slug2):
        lane_dir = repo / ".hypergraph" / "lanes" / slug
        assert lane_dir.is_dir()
        branch = subprocess.run(
            ["git", "-C", str(lane_dir), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, check=True).stdout.strip()
        assert branch == f"lane/{slug}"


def test_open_without_an_agent_stands_down_at_exit_zero_with_manual_steps(
        tmp_path, capsys):
    """The push/no-mirror posture: the zero-code fallback ships as printed text."""
    repo = lane_repo(tmp_path)
    code, slug, out = open_lane(capsys, repo, "--at", "within some-node-0001")
    assert code == 0
    assert "no `dispatch.agent` configured" in out
    assert "hypergraph-dispatch" in out                  # the skill to follow
    assert f"dispatch harvest {slug}" in out
    assert f"dispatch close {slug}" in out
    assert "within some-node-0001" in out                # the target survives


# ------------------------------------------------------------- the agent launch

def test_agent_gets_the_brief_on_stdin_and_nothing_secret_in_argv(
        tmp_path, capsys):
    """backend/lanes.md ops 2–3: stdin has one reader; argv is world-readable."""
    repo = lane_repo(tmp_path)
    capture = tmp_path / "seen.json"
    agent = tmp_path / "agent.py"
    agent.write_text(
        "import json, sys\n"
        "json.dump({'argv': sys.argv[1:], 'stdin': sys.stdin.read()},\n"
        f"          open({str(capture)!r}, 'w'))\n")
    config_path(repo).write_text(
        "project: t\ngraph_dir: .hypergraph/graph\n"
        f"dispatch:\n  agent: \"{sys.executable} {agent} --cwd {{lane_dir}}\"\n")
    code, slug, _out = open_lane(capsys, repo, "--at", "hollow-rain-8997",
                                 "--budget", "2")
    assert code == 0
    seen = json.loads(capture.read_text())
    brief = json.loads(seen["stdin"])
    assert brief["target"] == "hollow-rain-8997"
    assert brief["budget"] == 2
    assert brief["lane"] == slug
    # argv carries the lane path placeholder and nothing about the dispatch
    assert any(slug in a for a in seen["argv"])          # {lane_dir} substituted
    assert not any("hollow-rain" in a for a in seen["argv"])
    assert not any("budget" in a.lower() for a in seen["argv"])


def test_agent_exit_status_passes_through_as_a_harness_fact(tmp_path, capsys):
    repo = lane_repo(tmp_path)
    agent = tmp_path / "agent.py"
    agent.write_text("import sys; sys.stdin.read(); sys.exit(3)\n")
    config_path(repo).write_text(
        "project: t\ngraph_dir: .hypergraph/graph\n"
        f"dispatch:\n  agent: \"{sys.executable} {agent}\"\n")
    code, _slug, _out = open_lane(capsys, repo)
    assert code == 3


# ------------------------------------------------------------------- harvesting

def test_harvest_merges_the_lane_and_reports_arrived_record_nodes(
        tmp_path, capsys):
    repo = lane_repo(tmp_path)
    _code, slug, _ = open_lane(capsys, repo)
    lane_dir = repo / ".hypergraph" / "lanes" / slug
    node = lane_dir / ".hypergraph" / "graph" / "record" / "shiny-lane-0042.md"
    node.write_text("---\nnode_id: x\nslug: shiny-lane-0042\ntitle: 'Dispatch: t'\n"
                    "created_at: '2026-08-16T00:00:00+00:00'\nparents:\n"
                    "- calm-fern-1003\n---\n## What\n\nwork\n")
    subprocess.run(["git", "-C", str(lane_dir), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(lane_dir), "-c", "user.email=t@e",
                    "-c", "user.name=t", "commit", "-qm", "record"], check=True)
    capsys.readouterr()
    assert dispatch(repo, "harvest", slug) == 0
    out = capsys.readouterr().out
    assert "shiny-lane-0042" in out and "1 record node(s) arrived" in out
    assert "reconcile pending" in out
    assert (repo / ".hypergraph" / "graph" / "record" / "shiny-lane-0042.md").exists()


def test_harvest_refuses_a_dirty_lane(tmp_path, capsys):
    repo = lane_repo(tmp_path)
    _code, slug, _ = open_lane(capsys, repo)
    (repo / ".hypergraph" / "lanes" / slug / "uncommitted.txt").write_text("x\n")
    assert dispatch(repo, "harvest", slug) == 2
    assert "uncommitted changes" in capsys.readouterr().err


# --------------------------------------------------------------------- teardown

def test_close_refuses_an_unharvested_lane_without_force(tmp_path, capsys):
    """backend/lanes.md op 5: teardown refuses while unharvested."""
    repo = lane_repo(tmp_path)
    _code, slug, _ = open_lane(capsys, repo)
    lane_commit(repo, slug)
    assert dispatch(repo, "close", slug) == 2
    assert "unmerged" in capsys.readouterr().err
    assert (repo / ".hypergraph" / "lanes" / slug).is_dir()   # still there
    assert dispatch(repo, "harvest", slug) == 0
    assert dispatch(repo, "close", slug) == 0
    assert not (repo / ".hypergraph" / "lanes" / slug).exists()
    branches = subprocess.run(["git", "-C", str(repo), "branch",
                               "--format=%(refname:short)"],
                              capture_output=True, text=True, check=True).stdout
    assert f"lane/{slug}" not in branches.split()


def test_close_force_abandons_the_work_loudly(tmp_path, capsys):
    repo = lane_repo(tmp_path)
    _code, slug, _ = open_lane(capsys, repo)
    lane_commit(repo, slug)
    capsys.readouterr()
    assert dispatch(repo, "close", slug, "--force") == 0
    assert "abandoned" in capsys.readouterr().out
    assert not (repo / ".hypergraph" / "lanes" / slug).exists()


# --------------------------------------------------------------------------- ls

def test_ls_shows_lanes_and_live_claims(tmp_path, capsys):
    repo = lane_repo(tmp_path)
    _code, slug, _ = open_lane(capsys, repo)
    # a live claim: an unreconciled Dispatch: node with no closure descendant
    graph_record = repo / ".hypergraph" / "graph" / "record"
    (graph_record / "brisk-claim-0007.md").write_text(
        "---\nnode_id: y\nslug: brisk-claim-0007\n"
        "title: 'Dispatch: hollow-rain-8997'\n"
        "created_at: '2026-08-16T00:00:00+00:00'\nparents:\n- calm-fern-1003\n"
        "---\n## What\n\nlane claim\n")
    capsys.readouterr()
    assert dispatch(repo, "ls") == 0
    out = capsys.readouterr().out
    assert slug in out and "merged" in out
    assert "brisk-claim-0007" in out and "Dispatch: hollow-rain-8997" in out
    # closing the lineage retires the claim
    (graph_record / "brisk-done-0008.md").write_text(
        "---\nnode_id: z\nslug: brisk-done-0008\ntitle: 'Worked it'\n"
        "created_at: '2026-08-16T01:00:00+00:00'\nparents:\n- brisk-claim-0007\n"
        "---\n## Result\n\nDispatch closed: 1 unit(s), done.\n")
    assert dispatch(repo, "ls") == 0
    assert "brisk-claim-0007" not in capsys.readouterr().out
