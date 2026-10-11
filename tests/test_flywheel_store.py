"""The Flywheel local repository as the canonical store (backend/flywheel-repo-adapter.md).

These run the real `flywheel` CLI against throwaway repositories, so they skip when it
is absent or its Node is too old for local repositories (`^24.15 || >=25.7`). Every
test drives `tools/hypergraph.py` as a subprocess from inside a project checkout,
because the store is found from the checkout, not from flags.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools" / "hypergraph.py"
LOCAL = ROOT / "tools" / "fixtures" / "local-graph"


def _flywheel_local_ok() -> bool:
    if shutil.which("flywheel") is None or shutil.which("node") is None:
        return False
    out = subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip()
    m = re.match(r"v(\d+)\.(\d+)", out)
    if not m:
        return False
    major, minor = int(m[1]), int(m[2])
    return (major == 24 and minor >= 15) or (major == 25 and minor >= 7) or major > 25


pytestmark = pytest.mark.skipif(not _flywheel_local_ok(),
                                reason="needs the flywheel CLI on Node ^24.15 || >=25.7")


def hg(cwd: Path, *argv, check: bool = True) -> subprocess.CompletedProcess:
    env = {**os.environ, "HYPERGRAPH_FLYWHEEL_ANY_VERSION": "1"}
    p = subprocess.run([sys.executable, str(CLI), *map(str, argv)], cwd=cwd,
                       capture_output=True, text=True, env=env, timeout=600)
    if check and p.returncode:
        raise AssertionError(f"hypergraph {' '.join(map(str, argv))} → {p.returncode}\n"
                             f"{p.stdout}\n{p.stderr}")
    return p


def fw(repo: Path, *argv) -> dict:
    p = subprocess.run(["flywheel", *argv, "--repo", str(repo), "--format=json"],
                       capture_output=True, text=True, timeout=600)
    assert p.returncode == 0, p.stdout + p.stderr
    return json.loads(p.stdout)


def git(cwd: Path, *argv) -> str:
    return subprocess.run(["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t",
                           *argv], cwd=cwd, capture_output=True, text=True, check=True).stdout


@pytest.fixture()
def project(tmp_path) -> Path:
    """A git checkout whose graphs are the local-graph fixture, kept in a Flywheel store."""
    proj = tmp_path / "proj"
    (proj / ".hypergraph").mkdir(parents=True)
    shutil.copytree(LOCAL / "graph", proj / ".hypergraph" / "graph")
    record_root = "wise-anchor-1001"
    state_root = "bright-harbor-2001"
    import uuid
    ns = None
    for line in CLI.read_text().splitlines():
        if line.startswith("HYPERGRAPH_NS"):
            ns = uuid.UUID(re.search(r'"([0-9a-f-]{36})"', line)[1])
    (proj / ".hypergraph" / "config.yml").write_text(
        "project: fixture\n"
        f"record_root:\n  node_id: {uuid.uuid5(ns, record_root)}\n  slug: {record_root}\n"
        f"state_root:\n  node_id: {uuid.uuid5(ns, state_root)}\n  slug: {state_root}\n"
        "cache_dir: .hypergraph/cache\nstate_md: STATE.md\ngraph_dir: .hypergraph/graph\n"
        "store:\n  kind: flywheel-repo\n  flywheel_cli: 0.2.78\n")
    (proj / ".gitignore").write_text(".flywheel/\n.hypergraph/graph/\n.hypergraph/store/\n"
                                     ".hypergraph/cache/\n")
    (proj / "README.md").write_text("fixture\n")
    git(proj, "init", "-q", "-b", "main")
    git(proj, "add", "-A")
    git(proj, "commit", "-qm", "init")
    out = hg(proj, "store", "init", "--config", ".hypergraph/config.yml")
    assert "imported 5 node(s)" in out.stdout
    return proj


def files_of(proj: Path) -> dict[str, str]:
    graph = proj / ".hypergraph" / "graph"
    return {str(p.relative_to(graph)): p.read_text() for p in sorted(graph.rglob("*.md"))}


def body(tmp_path: Path, text: str) -> Path:
    p = tmp_path / f"body-{abs(hash(text))}.md"
    p.write_text(text)
    return p


def test_init_imports_every_node_and_a_fresh_working_copy_is_byte_identical(project):
    before = files_of(project)
    assert hg(project, "store", "verify", "--config", ".hypergraph/config.yml").returncode == 0
    shutil.rmtree(project / ".hypergraph" / "graph")
    shutil.rmtree(project / ".hypergraph" / "store")
    hg(project, "store", "pull", "--full", "--config", ".hypergraph/config.yml")
    assert files_of(project) == before


def test_the_store_mirrors_slugs_parents_and_containment(project):
    listed = fw(project, "repo:node:list")["nodes"]
    assert len(listed) == 5
    index = json.loads((project / ".hypergraph/store/index.json").read_text())
    calm = index["nodes"]["calm-fern-1003"]
    node = fw(project, "repo:node:get", calm["id"])["node"]
    assert node["slug_name"] == "calm-fern-1003" and node["origin_host"] == "hypergraph"
    parents = {r["parent_node_id"] for r in fw(project, "repo:lineage:list", calm["id"])["relations"]
               if r["child_node_id"] == calm["id"]}
    assert parents == {index["nodes"][p]["id"] for p in calm["parents"]}
    contained = {n["node_id"] for n in listed
                 if n.get("container_node_id") == index["nodes"]["wise-anchor-1001"]["id"]}
    assert calm["id"] in contained


def test_a_new_record_is_committed_to_the_store_with_its_command_as_message(project, tmp_path):
    out = hg(project, "new", "record", "--config", ".hypergraph/config.yml", "--title", "Probe",
             "--body", body(tmp_path, "## What\n\nprobe\n"), "--parent", "calm-fern-1003",
             "--none", "test")
    slug = out.stdout.split()[0]
    assert "1 node(s) committed" in out.stderr
    log = fw(project, "repo:log")["commits"]
    assert log[0]["message"].startswith("hypergraph new record")
    assert hg(project, "store", "verify", "--config", ".hypergraph/config.yml").returncode == 0
    assert (project / ".hypergraph/graph/record" / f"{slug}.md").is_file()


def test_a_state_update_and_reparent_reach_the_store(project, tmp_path):
    cfg = ("--config", ".hypergraph/config.yml")
    expect = hg(project, "update", "quiet-summit-2002", "--print-sha", *cfg).stdout.strip()
    text = (project / ".hypergraph/graph/state/quiet-summit-2002.md").read_text()
    current = text.split("\n---\n", 1)[1]
    hg(project, "update", "quiet-summit-2002", "--body", body(tmp_path, current + "\nMore.\n"),
       "--expect", expect, "--reconcile", *cfg)
    assert hg(project, "store", "verify", *cfg).returncode == 0
    index = json.loads((project / ".hypergraph/store/index.json").read_text())
    node = fw(project, "repo:node:get", index["nodes"]["quiet-summit-2002"]["id"])["node"]
    assert "More." in node["content"]


def test_a_worktree_writes_into_the_main_checkouts_graph_and_store(project, tmp_path):
    wt = tmp_path / "wt"
    git(project, "worktree", "add", "-q", "-b", "side", str(wt))
    assert not (wt / ".hypergraph" / "graph").exists()
    out = hg(wt, "new", "record", "--title", "From a worktree",
             "--body", body(tmp_path, "## What\n\nside\n"), "--parent", "calm-fern-1003",
             "--none", "test")
    slug = out.stdout.split()[0]
    assert (project / ".hypergraph/graph/record" / f"{slug}.md").is_file()
    assert not (wt / ".hypergraph" / "graph").exists()
    assert hg(project, "store", "verify", "--config", ".hypergraph/config.yml").returncode == 0


def test_concurrent_writers_each_get_their_own_commit(project, tmp_path):
    results = []

    def write(i):
        results.append(hg(project, "new", "record", "--config", ".hypergraph/config.yml",
                          "--title", f"Writer {i}", "--body", body(tmp_path, f"## What\n\n{i}\n"),
                          "--parent", "calm-fern-1003", "--none", "test", check=False))

    threads = [threading.Thread(target=write, args=(i,)) for i in range(3)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert all(r.returncode == 0 for r in results), [r.stderr for r in results]
    messages = [c["message"] for c in fw(project, "repo:log")["commits"]]
    assert sum(m.startswith("hypergraph new record") for m in messages) == 3
    assert hg(project, "store", "verify", "--config", ".hypergraph/config.yml").returncode == 0


def test_a_change_made_in_the_store_is_pulled_into_the_working_copy(project, tmp_path):
    """Another machine's commit arriving by `flywheel repo:pull`, simulated in place."""
    index = json.loads((project / ".hypergraph/store/index.json").read_text())
    fid = index["nodes"]["brave-otter-1002"]["id"]
    node = fw(project, "repo:node:get", fid)["node"]
    marker = node["content"].rfind("\n<!-- hypergraph:")
    edited = node["content"][:marker] + "\nAdded elsewhere.\n" + node["content"][marker:]
    fw(project, "repo:node:set", fid, "--field", "content", "--value-file", body(tmp_path, edited))
    fw(project, "repo:commit", "--message", "elsewhere")
    hg(project, "export", "--config", ".hypergraph/config.yml")   # any non-read command refreshes
    text = (project / ".hypergraph/graph/record/brave-otter-1002.md").read_text()
    assert "Added elsewhere." in text


def test_a_local_edit_racing_a_store_edit_is_refused_not_overwritten(project, tmp_path):
    index = json.loads((project / ".hypergraph/store/index.json").read_text())
    fid = index["nodes"]["brave-otter-1002"]["id"]
    node = fw(project, "repo:node:get", fid)["node"]
    marker = node["content"].rfind("\n<!-- hypergraph:")
    fw(project, "repo:node:set", fid, "--field", "content",
       "--value-file", body(tmp_path, node["content"][:marker] + "\nremote\n" + node["content"][marker:]))
    fw(project, "repo:commit", "--message", "remote")
    path = project / ".hypergraph/graph/record/brave-otter-1002.md"
    path.write_text(path.read_text() + "\nlocal\n")
    out = hg(project, "export", "--config", ".hypergraph/config.yml", check=False)
    assert out.returncode == 2 and "changed both" in out.stderr
    assert path.read_text().endswith("\nlocal\n")


def test_a_pinned_cli_version_mismatch_refuses_to_write(project, tmp_path):
    cfg = project / ".hypergraph/config.yml"
    cfg.write_text(cfg.read_text().replace("flywheel_cli: 0.2.78", "flywheel_cli: 0.0.1"))
    env = {k: v for k, v in os.environ.items() if k != "HYPERGRAPH_FLYWHEEL_ANY_VERSION"}
    p = subprocess.run([sys.executable, str(CLI), "store", "push", "--config", str(cfg)],
                       cwd=project, capture_output=True, text=True, env=env)
    assert p.returncode == 2 and "pins 0.0.1" in p.stderr


def test_check_since_counts_records_created_after_the_fork(project, tmp_path):
    git(project, "switch", "-q", "-c", "work")
    (project / "code.py").write_text("x = 1\n")
    git(project, "add", "code.py")
    git(project, "commit", "-qm", "work")
    cfg = ("--config", ".hypergraph/config.yml")
    hg(project, "export", *cfg)
    args = ("check", "--record", ".hypergraph/cache/record.json",
            "--state", ".hypergraph/cache/state.json", *cfg, "--since", "main")
    assert hg(project, *args, check=False).returncode == 1
    hg(project, "new", "record", *cfg, "--title", "The work",
       "--body", body(tmp_path, "## What\n\ncode\n"), "--parent", "calm-fern-1003", "--none", "t")
    hg(project, "export", *cfg)
    out = hg(project, *args, check=False)
    assert "record node(s) for 1 changed file(s)" in out.stdout, out.stdout
