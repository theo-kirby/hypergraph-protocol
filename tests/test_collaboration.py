"""Parallel and multi-contributor work: merges, forks, pull requests, cloud fleets.

The properties worth the most here are the three defects reproduced in
[rec: vast-rain-4873], because each one loses work *silently* — the checker reported
0 violations in all three cases before this suite existed:

- a merged record node dropping out of the frontier because the high-water mark was
  compared by timestamp rather than by ancestry;
- a git conflict-marker block passing `check` and reaching the append-only mirror;
- `push` publishing from a branch that may never merge.
"""
import json
import subprocess
from pathlib import Path

import pytest

from graph_fixtures import hg


def run(*argv):
    return hg.main([str(a) for a in argv])


def run_out(capsys, *argv):
    capsys.readouterr()
    code = run(*argv)
    cap = capsys.readouterr()
    return code, cap.out, cap.err


# ------------------------------------------------------------------ graph builder

def node(slug, created, parents=(), *, content=None, title=None):
    return hg.Node(node_id=hg.node_id_for(slug), slug=slug, title=title or slug,
                   content=content if content is not None else "body\n\n## State Impact\n\nnone: demo\n",
                   parent_ids=[hg.node_id_for(p) for p in parents], created_at=created)


def graph(*nodes):
    return hg.Graph(nodes={n.node_id: n for n in nodes},
                    by_slug={n.slug: n for n in nodes})


def merged_history():
    """The exact shape from the investigation, and the shape this repo already has.

        root ── alice (10:00, on main)
          └──── bob   (09:30, on a branch that merged afterwards)

    Bob is *older* than Alice but is not her ancestor. Any timestamp rule anchored on
    Alice counts him as reconciled; ancestry does not.
    """
    root = node("record-root-0000", "2026-08-09T09:00:00+00:00")
    bob = node("bobs-node-0001", "2026-08-09T09:30:00+00:00", ["record-root-0000"])
    alice = node("alice-node-0002", "2026-08-09T10:00:00+00:00", ["record-root-0000"])
    return graph(root, bob, alice), root


# ------------------------------------------------- I5: the frontier is an ancestry set

def test_a_node_merged_from_an_older_branch_is_not_silently_reconciled():
    """The headline defect. Bob predates the mark and was never folded."""
    record, root = merged_history()
    pending = hg.unreconciled_nodes(record, ["alice-node-0002"], root)
    assert [n.slug for n in pending] == ["bobs-node-0001"]


def test_a_frontier_of_both_tips_covers_both_branches():
    record, root = merged_history()
    assert hg.unreconciled_nodes(record, ["alice-node-0002", "bobs-node-0001"], root) == []


def test_a_linear_graph_behaves_exactly_as_before():
    """Backward compatibility: one slug, one chain, same answer as the timestamp rule."""
    root = node("record-root-0000", "2026-08-09T09:00:00+00:00")
    a = node("first-node-0001", "2026-08-09T09:30:00+00:00", ["record-root-0000"])
    b = node("second-node-0002", "2026-08-09T10:00:00+00:00", ["first-node-0001"])
    record = graph(root, a, b)
    assert hg.unreconciled_nodes(record, ["first-node-0001"], root) == [b]
    assert hg.unreconciled_nodes(record, ["second-node-0002"], root) == []


def test_an_empty_frontier_means_nothing_is_reconciled():
    record, root = merged_history()
    assert len(hg.unreconciled_nodes(record, [], root)) == 2


def test_read_hwm_parses_one_slug_a_list_and_none():
    def frontier_of(line):
        content = f"body\n\n## Reconciliation\n\n- high_water_mark: {line}\n- reconciled_at: x\n"
        return hg.read_hwm(node("state-root-0000", "x", content=content))[0]

    assert frontier_of("only-node-0001") == ["only-node-0001"]
    assert frontier_of("a-node-0001, b-node-0002") == ["a-node-0001", "b-node-0002"]
    assert frontier_of("a-node-0001,b-node-0002") == ["a-node-0001", "b-node-0002"]
    assert frontier_of("none") == []
    # round-trips through the writer
    assert hg.format_hwm(["a-node-0001", "b-node-0002"]) == "a-node-0001, b-node-0002"
    assert hg.format_hwm([]) == "none"


def test_a_duplicated_tip_is_collapsed():
    content = ("body\n\n## Reconciliation\n\n"
               "- high_water_mark: a-node-0001, a-node-0001\n- reconciled_at: x\n")
    assert hg.read_hwm(node("state-root-0000", "x", content=content))[0] == ["a-node-0001"]


def test_ancestors_of_ignores_a_slug_it_cannot_resolve():
    """The caller reports unknown slugs as violations; the walk must not raise first."""
    record, _root = merged_history()
    assert hg.ancestors_of(record, ["absent-node-9999"]) == set()


def test_check_reports_every_unresolvable_tip_by_name(tmp_path, capsys):
    record, root = merged_history()
    state_root = node("state-root-0000", "2026-08-09T11:00:00+00:00", content=(
        "body\n\n## Reconciliation\n\n"
        "- high_water_mark: alice-node-0002, ghost-node-9999\n"
        "- reconciled_at: 2026-08-09T11:00:00+00:00\n"))
    report = hg.Report()
    hg.check_hwm(record, graph(state_root), root, state_root, report)
    messages = [str(f) for f in report.violations()]
    assert len(messages) == 1 and "ghost-node-9999" in messages[0]


def test_the_migration_hint_fires_only_for_nodes_predating_the_mark():
    """A pre-0.0.5 graph surfaces already-folded side branches. Say so, or the upgrade
    reads as "your work vanished"."""
    record, root = merged_history()
    state_root = node("state-root-0000", "2026-08-09T11:00:00+00:00", content=(
        "body\n\n## Reconciliation\n\n- high_water_mark: alice-node-0002\n"
        "- reconciled_at: 2026-08-09T11:00:00+00:00\n"))
    report = hg.Report()
    hg.check_hwm(record, graph(state_root), root, state_root, report)
    infos = [str(f) for f in report.infos()]
    assert any("hwm --suggest" in m for m in infos)
    assert not report.violations()  # never a failure: this is not new work


def test_genuinely_new_work_does_not_trigger_the_migration_hint():
    record, root = merged_history()
    late = node("later-node-0003", "2026-08-09T12:00:00+00:00", ["alice-node-0002"])
    record.nodes[late.node_id] = late
    record.by_slug[late.slug] = late
    state_root = node("state-root-0000", "x", content=(
        "body\n\n## Reconciliation\n\n"
        "- high_water_mark: alice-node-0002, bobs-node-0001\n"
        "- reconciled_at: 2026-08-09T11:00:00+00:00\n"))
    report = hg.Report()
    hg.check_hwm(record, graph(state_root), root, state_root, report)
    infos = [str(f) for f in report.infos()]
    assert any("1 unreconciled" in m for m in infos)
    assert not any("hwm --suggest" in m for m in infos)


def test_suggest_frontier_returns_the_tips_the_old_rule_covered():
    record, root = merged_history()
    assert hg.suggest_frontier(record, ["alice-node-0002"], root) == [
        "bobs-node-0001", "alice-node-0002"]


def test_suggest_frontier_omits_a_node_that_has_a_covered_child():
    """Only maximal elements: listing every ancestor would be noise."""
    root = node("record-root-0000", "2026-08-09T09:00:00+00:00")
    a = node("first-node-0001", "2026-08-09T09:30:00+00:00", ["record-root-0000"])
    b = node("second-node-0002", "2026-08-09T10:00:00+00:00", ["first-node-0001"])
    assert hg.suggest_frontier(graph(root, a, b), ["second-node-0002"], root) == [
        "second-node-0002"]


# ------------------------------------------------------- git conflict markers

CONFLICTED = ("Some prose.\n\n<<<<<<< HEAD\nmine\n=======\ntheirs\n>>>>>>> feature\n\n"
              "## State Impact\n\nnone: demo\n")


def test_a_conflict_marker_is_a_violation():
    report = hg.Report()
    hg.check_conflict_markers(graph(node("some-node-0001", "x", content=CONFLICTED)), report)
    assert len(report.violations()) == 1
    assert "conflict marker" in str(report.violations()[0])


def test_diff3_style_common_ancestor_markers_are_caught():
    body = "a\n<<<<<<< ours\nx\n||||||| base\ny\n=======\nz\n>>>>>>> theirs\n"
    report = hg.Report()
    hg.check_conflict_markers(graph(node("some-node-0001", "x", content=body)), report)
    assert report.violations()


def test_a_setext_heading_underline_is_not_a_conflict_marker():
    """`=======` is also markdown. Flagging it alone would fail honest documents."""
    body = "A real heading\n=======\n\nprose\n\nAnd another\n-------\n"
    report = hg.Report()
    hg.check_conflict_markers(graph(node("some-node-0001", "x", content=body)), report)
    assert not report.violations()


def test_a_fenced_code_block_about_merging_is_not_flagged():
    body = "Explaining merges:\n\n    <<<<<<< HEAD is what git writes\n\nprose\n"
    report = hg.Report()
    hg.check_conflict_markers(graph(node("some-node-0001", "x", content=body)), report)
    assert not report.violations()  # indented, so not at line start


def test_a_conflicted_body_is_refused_at_authoring_time(tmp_path, capsys):
    """`check` runs in CI; this runs on the machine that would have committed it."""
    graph_dir = tmp_path / "graph"
    body = tmp_path / "b.md"
    body.write_text("root overview\n")
    assert run("new", "record", "--graph-dir", graph_dir, "--root",
               "--title", "demo — record", "--body", body) == 0
    root_slug = next((graph_dir / "record").glob("*.md")).stem
    body.write_text(CONFLICTED.replace("\n\n## State Impact\n\nnone: demo\n", "\n"))
    code, _out, err = run_out(capsys, "new", "record", "--graph-dir", graph_dir,
                              "--title", "conflicted", "--parent", root_slug,
                              "--body", body, "--none", "demo")
    assert code == 2 and "conflict marker" in err.lower()


def test_check_flags_conflict_markers_end_to_end(tmp_path, capsys):
    exports = tmp_path / "e"
    exports.mkdir()
    (exports / "record.json").write_text(json.dumps({"version": 1, "nodes": [
        {"node_id": hg.node_id_for("record-root-0000"), "slug_name": "record-root-0000",
         "title": "r", "content": "root\n", "parent_ids": []},
        {"node_id": hg.node_id_for("some-node-0001"), "slug_name": "some-node-0001",
         "title": "n", "content": CONFLICTED,
         "parent_ids": [hg.node_id_for("record-root-0000")]}]}))
    (exports / "state.json").write_text(json.dumps({"version": 1, "nodes": [
        {"node_id": hg.node_id_for("state-root-0000"), "slug_name": "state-root-0000",
         "title": "s", "parent_ids": [],
         "content": "root\n\n## Reconciliation\n\n- high_water_mark: none\n"
                    "- reconciled_at: 2026-08-09T11:00:00+00:00\n"}]}))
    code, out, _err = run_out(capsys, "check", "--record", exports / "record.json",
                              "--state", exports / "state.json")
    assert code == 1 and "conflict marker" in out


# --------------------------------------------------------------- publish branch

def git_repo(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    (tmp_path / "f.txt").write_text("hi\n")
    for args in (["add", "-A"], ["-c", "user.email=t@e", "-c", "user.name=t",
                                 "commit", "-qm", "init"]):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True)
    return tmp_path


def test_publish_is_allowed_on_the_default_branch(tmp_path):
    assert hg.publish_branch_block({}, cwd=git_repo(tmp_path)) is None


def test_publish_is_blocked_on_a_feature_branch(tmp_path):
    repo = git_repo(tmp_path)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "feature"], check=True)
    blocked = hg.publish_branch_block({}, cwd=repo)
    assert blocked and "feature" in blocked and "main" in blocked


def test_publish_branch_is_configurable(tmp_path):
    repo = git_repo(tmp_path)
    assert hg.publish_branch_block({"publish_branch": "release"}, cwd=repo)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "release"], check=True)
    assert hg.publish_branch_block({"publish_branch": "release"}, cwd=repo) is None


def test_a_detached_head_is_blocked(tmp_path):
    repo = git_repo(tmp_path)
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", sha], check=True)
    blocked = hg.publish_branch_block({}, cwd=repo)
    assert blocked and "detached" in blocked


def test_a_graph_outside_git_is_not_blocked(tmp_path):
    """The node files are the graph; git is how they usually travel, not a requirement."""
    assert hg.publish_branch_block({}, cwd=tmp_path) is None


# ------------------------------------------------------------- mirror ownership

class Auth:
    def __init__(self, **status):
        self.status = status

    def auth_status(self):
        if isinstance(self.status, BaseException):
            raise self.status
        return self.status


def test_the_owners_credentials_publish():
    assert hg.mirror_not_ours({"mirror_account_id": "acct-1"},
                              Auth(authenticated=True, user_id="acct-1")) is None


def test_a_contributors_credentials_stand_down():
    reason = hg.mirror_not_ours({"mirror_account_id": "acct-1"},
                                Auth(authenticated=True, user_id="acct-2"))
    assert reason and "acct-2" in reason and "acct-1" in reason


def test_being_logged_out_stands_down():
    assert "not authenticated" in hg.mirror_not_ours({}, Auth(authenticated=False))


def test_without_a_configured_account_ownership_is_not_asserted():
    """No `mirror_account_id:` means there is nothing to compare — preflight decides."""
    assert hg.mirror_not_ours({}, Auth(authenticated=True, user_id="acct-2")) is None


# ------------------------------------------------------------------ check --since

def recorded_repo(tmp_path):
    repo = git_repo(tmp_path)
    graph_dir = repo / ".hypergraph" / "graph"
    body = repo / "b.md"
    body.write_text("overview\n")
    assert run("new", "record", "--graph-dir", graph_dir, "--root",
               "--title", "demo — record", "--body", body) == 0
    root_slug = next((graph_dir / "record").glob("*.md")).stem
    body.unlink()
    (repo / ".hypergraph").mkdir(exist_ok=True)
    config = repo / ".hypergraph" / "config.yml"
    config.write_text("project: demo\ngraph_dir: .hypergraph/graph\n"
                      "cache_dir: .hypergraph/cache\nstate_md: STATE.md\n")
    for args in (["add", "-A"], ["-c", "user.email=t@e", "-c", "user.name=t",
                                 "commit", "-qm", "graph"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "work"], check=True)
    return repo, graph_dir, root_slug


def commit_all(repo, message):
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@e", "-c", "user.name=t",
                    "commit", "-qm", message], check=True)


def since_report(repo, ref="main"):
    report = hg.Report()
    config = {"graph_dir": ".hypergraph/graph", "cache_dir": ".hypergraph/cache",
              "state_md": "STATE.md"}
    hg.check_since(ref, config, report, cwd=repo)
    return report


def test_a_branch_that_changes_code_without_recording_fails(tmp_path):
    repo, _graph_dir, _root = recorded_repo(tmp_path)
    (repo / "app.py").write_text("print('hi')\n")
    commit_all(repo, "code only")
    violations = [str(f) for f in since_report(repo).violations()]
    assert len(violations) == 1 and "app.py" in violations[0]


def test_a_branch_that_records_its_work_passes(tmp_path):
    repo, graph_dir, root_slug = recorded_repo(tmp_path)
    (repo / "app.py").write_text("print('hi')\n")
    body = repo / "note.md"
    body.write_text("did the thing\n")
    assert run("new", "record", "--graph-dir", graph_dir, "--title", "the work",
               "--parent", root_slug, "--body", body, "--none", "demo") == 0
    body.unlink()
    commit_all(repo, "code plus a record node")
    report = since_report(repo)
    assert not report.violations()
    assert any("1 record node(s)" in str(f) for f in report.infos())


def test_a_branch_that_only_touches_the_graph_needs_no_record_node(tmp_path):
    """A reconcile pass writes state nodes and STATE.md and records nothing. That is
    the protocol working, not a contributor skipping the obligation."""
    repo, graph_dir, _root = recorded_repo(tmp_path)
    (repo / "STATE.md").write_text("# regenerated\n")
    commit_all(repo, "reconcile output")
    report = since_report(repo)
    assert not report.violations()
    assert any("no work outside the graph" in str(f) for f in report.infos())


def test_a_missing_ref_names_the_shallow_clone_cause(tmp_path):
    repo, _graph_dir, _root = recorded_repo(tmp_path)
    violations = [str(f) for f in since_report(repo, "origin/nope").violations()]
    assert len(violations) == 1 and "fetch-depth" in violations[0]


def test_since_outside_a_git_checkout_is_a_violation_not_a_crash(tmp_path):
    violations = since_report(tmp_path).violations()
    assert len(violations) == 1 and "not a git checkout" in str(violations[0])
