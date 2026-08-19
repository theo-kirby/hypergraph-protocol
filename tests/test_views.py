"""Named views (SPEC: Views): N derived graphs over the record graph.

Three layers of coverage, in the order the feature was built:

1. **Back-compat goldens** — a project with no `views:` must behave byte-for-byte
   as before: `graph_kinds({})` is the old pair, the clean fixture's findings are
   pinned, and the local-graph fixture's export payload matches its committed
   snapshot.
2. **The grammar and the checker** — view-qualified impact targets parse (split
   before the NEW test), an unconfigured view is an I2 violation, and each view
   carries its own high-water mark with a per-view pending tally.
3. **The CLI end to end** — `views add` through `sync`, on a scratch project.
"""
import json
from pathlib import Path

import pytest

from graph_fixtures import CLEAN, FIXTURES, LOCAL, hg

VIEWS_POLICY = FIXTURES / "views-policy"
VIEWS_POLICY_CONFIG = {
    "record_root": {"node_id": "10000000-0000-0000-0000-000000000001",
                    "slug": "royal-anchor-0001"},
    "state_root": {"node_id": "20000000-0000-0000-0000-000000000001",
                   "slug": "amber-harbor-0101"},
    "views": {"policy": {"root": {"node_id": "30000000-0000-0000-0000-000000000001",
                                  "slug": "pale-meadow-0200"},
                         "md": "POLICY.md"}},
}


def run(*argv):
    return hg.main([str(a) for a in argv])


# ------------------------------------------------------ 1. back-compat goldens

def test_graph_kinds_without_config_is_the_old_pair():
    assert hg.graph_kinds({}) == ("record", "state")
    assert hg.graph_kinds({"project": "t"}) == ("record", "state")


def test_graph_kinds_with_views_extends_the_pair():
    assert hg.graph_kinds({"views": {"policy": {}}}) == ("record", "state", "policy")


def test_view_defs_state_is_always_view_one():
    defs = hg.view_defs({"state_root": {"slug": "a-b-0001"}, "state_md": "STATE.md"})
    assert list(defs) == ["state"]
    assert defs["state"] == {"root": {"slug": "a-b-0001"}, "md": "STATE.md"}


@pytest.mark.parametrize("views", [
    ["policy"],                      # not a mapping
    {"Policy": {}},                  # not kebab-case
    {"state": {}},                   # reserved: would shadow view #1
    {"record": {}},                  # reserved: not a view at all
    {"cache": {}},                   # reserved: the export directory
    {"policy": ["root"]},            # entry not a mapping
])
def test_view_defs_rejects_bad_shapes(views):
    with pytest.raises(hg.LocalGraphError):
        hg.view_defs({"views": views})


def test_clean_fixture_findings_are_pinned_byte_for_byte():
    """The Phase-1 golden: a project with no `views:` gets exactly the findings it
    always got — level, invariant, node ref and message all unchanged."""
    report = hg.run_check(CLEAN / "record.json", CLEAN / "state.json")
    assert [(f.level, f.invariant, f.node, f.message) for f in report.findings] == [
        ("info", "I5", "amber-harbor-0101",
         "0 unreconciled record node(s) past high-water mark"),
    ]


def test_export_payload_matches_the_committed_snapshot():
    """The other Phase-1 golden: the export a viewless graph produces is
    node-for-node the committed local-graph snapshot."""
    for kind in ("record", "state"):
        fresh = hg.export_graph_json(LOCAL / "graph", kind)["nodes"]
        committed = json.loads((LOCAL / f"{kind}.json").read_text())["nodes"]
        assert fresh == committed


# ------------------------------------------------- 2. the grammar, the checker

def test_parse_impacts_view_qualified_targets():
    entries, none_reason, bad = hg.parse_impacts(
        "- target: policy/NEW ppo-baseline — first policy line\n"
        "- target: policy/shy-cabin-0201 — status open → working\n"
        "- target: wild-fox-1234 — unqualified still means the state graph\n"
        "- target: NEW ingest-pipeline — unqualified NEW too\n")
    assert entries == [
        ("policy", "ppo-baseline", "first policy line", True),
        ("policy", "shy-cabin-0201", "status open → working", False),
        ("state", "wild-fox-1234", "unqualified still means the state graph", False),
        ("state", "ingest-pipeline", "unqualified NEW too", True),
    ]
    assert none_reason is None and bad == []


@pytest.mark.parametrize("line", [
    "- target: policy/ — nothing after the qualifier",
    "- target: Policy/wild-fox-1234 — view names are kebab-case",
    "- target: NEW policy/x — NEW binds inside the view, never outside",
    "- target: policy/NEW Bad_Name — the NEW name is still kebab-case",
    "- target: policy/not a slug — qualified target must be a slug or NEW",
])
def test_parse_impacts_rejects_bad_view_lines(line):
    entries, _none, bad = hg.parse_impacts(line)
    assert entries == [] and bad == [line.strip()]


def test_views_policy_fixture_checks_clean():
    report = hg.run_check(VIEWS_POLICY / "record.json", VIEWS_POLICY / "state.json",
                          VIEWS_POLICY_CONFIG)
    assert report.violations() == []
    assert report.warnings() == []
    # both views report their own reconciliation status
    unrec = [f for f in report.infos() if "unreconciled" in f.message]
    assert {f.node for f in unrec} == {"amber-harbor-0101", "pale-meadow-0200"}
    assert all(f.message.startswith("0 unreconciled") for f in unrec)


def test_missing_view_export_names_sync(tmp_path):
    """The config declares a view whose export is absent: exit-2 territory, with
    the regeneration command in the message — never a silent pass."""
    for name in ("record.json", "state.json"):
        (tmp_path / name).write_text((VIEWS_POLICY / name).read_text())
    with pytest.raises(hg.LocalGraphError) as err:
        hg.run_check(tmp_path / "record.json", tmp_path / "state.json",
                     VIEWS_POLICY_CONFIG)
    assert "hypergraph sync" in str(err.value)


def test_pending_impacts_tally_per_view(tmp_path):
    """Roll the policy HWM back to the record root: the policy impact goes
    pending under a view-prefixed key, and the state tally stays empty."""
    policy = json.loads((VIEWS_POLICY / "policy.json").read_text())
    policy["nodes"][0]["content"] = policy["nodes"][0]["content"].replace(
        "high_water_mark: bold-ember-0005", "high_water_mark: royal-anchor-0001")
    for name in ("record.json", "state.json"):
        (tmp_path / name).write_text((VIEWS_POLICY / name).read_text())
    (tmp_path / "policy.json").write_text(json.dumps(policy))

    report = hg.run_check(tmp_path / "record.json", tmp_path / "state.json",
                          VIEWS_POLICY_CONFIG)
    assert report.violations() == []
    pending = [f for f in report.infos() if "pending impact" in f.message]
    assert [f.node for f in pending] == ["policy/shy-cabin-0201"]
    unrec = {f.node: f.message for f in report.infos() if "unreconciled" in f.message}
    # the state graph is still fully reconciled; only the policy view has drift
    assert unrec["amber-harbor-0101"].startswith("0 unreconciled")
    assert unrec["pale-meadow-0200"].startswith("4 unreconciled")


def test_check_cli_over_the_views_fixture(tmp_path, capsys):
    """Through main(): the sibling-export derivation works from the CLI too."""
    import yaml
    config = tmp_path / "config.yml"
    config.write_text(yaml.safe_dump(VIEWS_POLICY_CONFIG, sort_keys=False))
    assert run("check", "--record", VIEWS_POLICY / "record.json",
               "--state", VIEWS_POLICY / "state.json", "--config", config) == 0
    out = capsys.readouterr().out
    assert "0 violation(s)" in out


# --------------------------------------------------------------- 3. the CLI

def scratch_project(tmp_path, monkeypatch):
    """`adopt --init` in a scratch dir, cwd inside it — the adopter's posture."""
    repo = tmp_path / "demo"
    repo.mkdir()
    monkeypatch.chdir(repo)
    config = repo / ".hypergraph" / "config.yml"
    assert run("adopt", "--init", "--repo", repo, "--project", "demo",
               "--config", config) == 0
    return repo, config


def roots_of(config):
    cfg = hg.load_config(config)
    return cfg["record_root"]["slug"], cfg["state_root"]["slug"]


def test_views_add_then_record_then_reconcile_then_sync(tmp_path, monkeypatch, capsys):
    """The whole life of a view, end to end: add → record a qualified impact →
    fold it with `new <view> --reconcile` → advance the view HWM → sync."""
    repo, config = scratch_project(tmp_path, monkeypatch)
    record_root, _state_root = roots_of(config)

    assert run("views", "add", "policy", "--md", "POLICY.md", "--reconcile",
               "--config", config) == 0
    out = capsys.readouterr().out
    assert "seeded with the current record tips" in out
    cfg = hg.load_config(config)
    policy_root = cfg["views"]["policy"]["root"]["slug"]
    assert cfg["views"]["policy"]["md"] == "POLICY.md"
    assert (repo / ".hypergraph" / "graph" / "policy" / f"{policy_root}.md").exists()

    # a record node may now declare a view-qualified impact
    assert run("new", "record", "--title", "Try PPO", "--parent", record_root,
               "--impact", "policy/NEW ppo-baseline — first policy line",
               "--config", config) == 0
    rec_slug = capsys.readouterr().out.split()[0]

    # fold it: a view node writes exactly like a state node, reconcile-gated
    body = tmp_path / "ppo.md"
    body.write_text(f"- PPO baseline attempted; evidence pending [rec: {rec_slug}].\n")
    assert run("new", "policy", "--title", "PPO baseline", "--parent", policy_root,
               "--status", "open", "--body", body,
               "--prov", f"{rec_slug} — initial evidence", "--reconcile",
               "--config", config) == 0
    capsys.readouterr()

    # advance the view's own high-water mark through the CAS
    root_file = repo / ".hypergraph" / "graph" / "policy" / f"{policy_root}.md"
    assert run("update", policy_root, "--print-sha", "--config", config) == 0
    sha = capsys.readouterr().out.strip()
    _meta, content = hg.split_frontmatter(root_file.read_text())
    body = tmp_path / "root-body.md"
    import re
    body.write_text(re.sub(r"high_water_mark: .*", f"high_water_mark: {rec_slug}",
                           content))
    assert run("update", policy_root, "--body", body, "--expect", sha,
               "--reconcile", "--config", config) == 0
    capsys.readouterr()

    assert run("sync", "--config", config) == 0
    out = capsys.readouterr().out
    assert (repo / ".hypergraph" / "cache" / "policy.json").exists()
    assert (repo / "POLICY.md").exists()
    rendered = (repo / "POLICY.md").read_text()
    assert rendered.startswith("# demo — policy view")
    assert "PPO baseline" in rendered
    # the state side is untouched by any of this
    assert "STATE.md" in out or (repo / "STATE.md").exists()
    assert "policy" not in (repo / "STATE.md").read_text()


def test_views_ls_lists_state_and_extras(tmp_path, monkeypatch, capsys):
    repo, config = scratch_project(tmp_path, monkeypatch)
    capsys.readouterr()
    assert run("views", "add", "policy", "--reconcile", "--config", config) == 0
    capsys.readouterr()
    assert run("views", "ls", "--config", config) == 0
    out = capsys.readouterr().out
    assert out.startswith("state")          # view #1, always listed first
    assert "\npolicy" in out
    assert "high_water_mark:" in out


@pytest.mark.parametrize("name,why", [
    ("Policy", "not kebab-case"),
    ("policy/x", "contains a slash"),
    ("state", "reserved"),
    ("record", "reserved"),
    ("cache", "reserved"),
    ("brave-otter-1002", "slug-shaped"),
])
def test_views_add_rejects_bad_names(tmp_path, monkeypatch, capsys, name, why):
    _repo, config = scratch_project(tmp_path, monkeypatch)
    assert run("views", "add", name, "--reconcile", "--config", config) == 2, why
    assert "views" not in hg.load_config(config)


def test_views_add_rejects_a_duplicate(tmp_path, monkeypatch, capsys):
    _repo, config = scratch_project(tmp_path, monkeypatch)
    assert run("views", "add", "policy", "--reconcile", "--config", config) == 0
    assert run("views", "add", "policy", "--reconcile", "--config", config) == 2
    assert "already exists" in capsys.readouterr().err


def test_views_add_requires_reconcile(tmp_path, monkeypatch, capsys):
    _repo, config = scratch_project(tmp_path, monkeypatch)
    assert run("views", "add", "policy", "--config", config) == 2
    assert "single" in capsys.readouterr().err


def test_two_views_share_one_config_block(tmp_path, monkeypatch, capsys):
    """The second `views add` inserts under the existing `views:` key — the
    config must stay one valid YAML mapping, comments intact."""
    _repo, config = scratch_project(tmp_path, monkeypatch)
    assert run("views", "add", "policy", "--reconcile", "--config", config) == 0
    assert run("views", "add", "reward-model", "--md", "REWARD.md",
               "--reconcile", "--config", config) == 0
    cfg = hg.load_config(config)
    assert set(cfg["views"]) == {"policy", "reward-model"}
    assert cfg["views"]["reward-model"]["md"] == "REWARD.md"
    assert hg.graph_kinds(cfg) == ("record", "state", "policy", "reward-model")


def test_new_record_refuses_an_unconfigured_view_impact(tmp_path, monkeypatch, capsys):
    """Authoring-time I2: the impact names a view nobody declared."""
    _repo, config = scratch_project(tmp_path, monkeypatch)
    record_root, _ = roots_of(config)
    assert run("new", "record", "--title", "T", "--parent", record_root,
               "--impact", "policy/NEW x — no such view", "--config", config) == 2
    assert "unconfigured view" in capsys.readouterr().err


def test_new_view_node_is_reconcile_gated_and_update_round_trips(
        tmp_path, monkeypatch, capsys):
    _repo, config = scratch_project(tmp_path, monkeypatch)
    record_root, _ = roots_of(config)
    assert run("views", "add", "policy", "--reconcile", "--config", config) == 0
    cfg = hg.load_config(config)
    policy_root = cfg["views"]["policy"]["root"]["slug"]
    capsys.readouterr()
    assert run("new", "record", "--title", "Evidence", "--parent", record_root,
               "--impact", "policy/NEW line — created", "--config", config) == 0
    rec_slug = capsys.readouterr().out.split()[0]

    # without --reconcile: refused, naming the single-writer rule
    assert run("new", "policy", "--title", "Line", "--parent", policy_root,
               "--status", "open", "--prov", f"{rec_slug} — why",
               "--config", config) == 2
    assert "single writer per view" in capsys.readouterr().err

    assert run("new", "policy", "--title", "Line", "--parent", policy_root,
               "--status", "open", "--prov", f"{rec_slug} — why",
               "--reconcile", "--config", config) == 0
    slug = capsys.readouterr().out.split()[0]

    # update: CAS + --reconcile, validated against the view's own graph
    assert run("update", slug, "--print-sha", "--config", config) == 0
    sha = capsys.readouterr().out.strip()
    assert run("update", slug, "--title", "Line v2", "--expect", sha,
               "--config", config) == 2          # missing --reconcile
    capsys.readouterr()
    assert run("update", slug, "--title", "Line v2", "--expect", sha,
               "--reconcile", "--config", config) == 0


def test_new_unknown_kind_exits_2(tmp_path, monkeypatch, capsys):
    _repo, config = scratch_project(tmp_path, monkeypatch)
    record_root, _ = roots_of(config)
    assert run("new", "nosuch", "--title", "T", "--parent", record_root,
               "--config", config) == 2
    assert "unknown graph kind" in capsys.readouterr().err


def test_artifacts_refused_on_a_view_node(tmp_path, monkeypatch, capsys):
    _repo, config = scratch_project(tmp_path, monkeypatch)
    assert run("views", "add", "policy", "--reconcile", "--config", config) == 0
    cfg = hg.load_config(config)
    policy_root = cfg["views"]["policy"]["root"]["slug"]
    capsys.readouterr()
    assert run("artifacts", "add", policy_root, "somefile.txt",
               "--config", config) == 2
    assert "view node" in capsys.readouterr().err


def test_newborn_view_has_zero_unreconciled(tmp_path, monkeypatch, capsys):
    """The seeded HWM means a late-born view starts caught up, not owing the
    whole record history a reconcile."""
    repo, config = scratch_project(tmp_path, monkeypatch)
    record_root, _ = roots_of(config)
    # some pre-view history
    assert run("new", "record", "--title", "Old work", "--parent", record_root,
               "--none", "predates the view", "--config", config) == 0
    assert run("views", "add", "policy", "--reconcile", "--config", config) == 0
    capsys.readouterr()
    assert run("sync", "--config", config) == 0
    capsys.readouterr()
    cache = repo / ".hypergraph" / "cache"
    assert run("hwm", "--record", cache / "record.json",
               "--state", cache / "state.json", "--view", "policy",
               "--config", config) == 0
    out = capsys.readouterr().out
    assert "0 unreconciled record node(s)" in out


def test_adopt_init_writes_no_views_block(tmp_path, monkeypatch):
    """Views are strictly post-init: a fresh config carries no `views:` key."""
    _repo, config = scratch_project(tmp_path, monkeypatch)
    assert "views" not in hg.load_config(config)
    assert "views" not in config.read_text()


def test_upgrade_config_stamp_leaves_the_views_block_alone():
    """`upgrade` re-stamps `hypergraph_version:` as a line edit — a views block
    below it must come through byte-identical."""
    text = ("project: demo\n\nhypergraph_version: 0.0.1\n\n"
            "views:\n  policy:\n    root:\n"
            "      node_id: 30000000-0000-0000-0000-000000000001\n"
            "      slug: pale-meadow-0200\n    md: POLICY.md\n")
    stamped = hg.stamp_config_version(text, hg.__version__)
    assert f"hypergraph_version: {hg.__version__}" in stamped
    assert stamped.split("views:", 1)[1] == text.split("views:", 1)[1]


def test_bare_project_sync_output_is_view_free(tmp_path, monkeypatch, capsys):
    """A project that never adds a view sees exactly the two classic exports."""
    repo, config = scratch_project(tmp_path, monkeypatch)
    capsys.readouterr()
    assert run("sync", "--config", config) == 0
    out = capsys.readouterr().out
    cache = repo / ".hypergraph" / "cache"
    assert sorted(p.name for p in cache.glob("*.json")) == ["record.json",
                                                            "state.json"]
    assert "record.json" in out and "state.json" in out
