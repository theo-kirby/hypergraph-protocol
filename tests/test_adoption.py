"""Adoption: the survey, the roots, the epoch marker, and the documented order.

Adoption is the one workflow no outside project had ever run, and its most expensive
defect was an *ordering* bug — the skill told the agent to author prehistory in step 2
and mint the roots in step 5, but `new record` needs a root to parent on, so the
documented sequence hard-errored at `adopt --init` and `--force` did not recover. The
agent's only remaining move was hand-writing the config, which is the exact failure
`--init` exists to prevent.

So the property worth the most here is `test_the_documented_mode_b_order_runs`: it
scripts the workflow *as the skill states it* and asserts exit 0 at every step. A
wrong order is invisible until an adopter hits it once, which is how that defect
survived to a real repo.
"""
import json
import subprocess
from pathlib import Path

from graph_fixtures import CLEAN, hg

ROOT = Path(__file__).resolve().parents[1]


def run(*argv):
    return hg.main([str(a) for a in argv])


def run_out(capsys, *argv):
    capsys.readouterr()
    code = run(*argv)
    return code, capsys.readouterr().out


def scratch_repo(tmp_path):
    """A tiny repo with a real git history, for the survey."""
    repo = tmp_path / "adoptee"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "main.py").write_text("print('hi')\n")
    (repo / "README.md").write_text("# adoptee\n\nA project with a past.\n")
    (repo / "pyproject.toml").write_text("[project]\nname='adoptee'\n")
    (repo / "tests").mkdir()
    import subprocess as sp
    sp.run(["git", "init", "-q"], cwd=repo, check=True)
    sp.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    sp.run(["git", "config", "user.name", "Tester"], cwd=repo, check=True)
    sp.run(["git", "add", "-A"], cwd=repo, check=True)
    sp.run(["git", "commit", "-qm", "first commit"], cwd=repo, check=True)
    return repo


def test_survey_reports_git_shape_layout_and_onboarding(tmp_path):
    repo = scratch_repo(tmp_path)
    survey = hg.adopt_survey(repo)
    assert survey["git"]["is_repo"] and survey["git"]["commits"] == 1
    assert survey["git"]["contributors"][0]["name"] == "Tester"
    assert {"path": "src", "files": 1} in survey["layout"]["source_dirs"]
    assert "README.md" in survey["layout"]["docs"]
    assert "pytest" in survey["layout"]["tests"]
    assert survey["layout"]["already_adopted"] is False


def test_survey_reports_a_claude_md_symlink_rather_than_making_the_agent_readlink(tmp_path):
    """adopt must never break a CLAUDE.md → AGENTS.md symlink. Make it mechanical."""
    repo = scratch_repo(tmp_path)
    (repo / "AGENTS.md").write_text("# Agents\n")
    (repo / "CLAUDE.md").symlink_to("AGENTS.md")
    onboarding = hg.adopt_survey(repo)["layout"]["onboarding"]
    assert onboarding["CLAUDE.md"]["is_symlink"] is True
    assert onboarding["CLAUDE.md"]["target"] == "AGENTS.md"
    assert onboarding["CLAUDE.md"]["target_exists"] is True
    assert onboarding["AGENTS.md"]["is_symlink"] is False
    assert onboarding["AGENTS.md"]["has_hypergraph_block"] is False


def test_survey_of_a_non_repo_does_not_crash(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert hg.adopt_survey(plain)["git"]["commits"] == 0


def test_adopt_init_writes_a_config_that_checks_clean(tmp_path, capsys):
    """A hand-written stub config once made `check` report 0 violations falsely, by
    silently guessing the roots. This writes a real one."""
    repo = scratch_repo(tmp_path)
    graph_dir = repo / ".hypergraph" / "graph"
    config = repo / ".hypergraph" / "config.yml"
    assert run("adopt", "--repo", repo, "--init", "--config", config,
               "--graph-dir", graph_dir) == 0
    capsys.readouterr()
    cache = tmp_path / "cache"
    assert run("export", "--graph-dir", graph_dir, "--out-dir", cache) == 0
    report = hg.run_check(cache / "record.json", cache / "state.json",
                          hg.load_config(config), config_given=True)
    assert report.violations() == [] and report.warnings() == []
    capsys.readouterr()


def test_adopt_init_refuses_to_overwrite_an_initialized_project(tmp_path, capsys):
    repo = scratch_repo(tmp_path)
    config = repo / ".hypergraph" / "config.yml"
    graph_dir = repo / ".hypergraph" / "graph"
    run("adopt", "--repo", repo, "--init", "--config", config, "--graph-dir", graph_dir)
    assert run("adopt", "--repo", repo, "--init", "--config", config,
               "--graph-dir", graph_dir) == 2
    assert "already exists" in capsys.readouterr().err


def test_adopt_marker_refuses_a_slug_that_does_not_resolve(tmp_path, capsys):
    """An unresolvable marker exempts nothing, silently — every legacy node then
    fails I2 instead of being legacy."""
    repo = scratch_repo(tmp_path)
    config = repo / ".hypergraph" / "config.yml"
    graph_dir = repo / ".hypergraph" / "graph"
    run("adopt", "--repo", repo, "--init", "--config", config, "--graph-dir", graph_dir)
    capsys.readouterr()
    assert run("adopt", "--repo", repo, "--marker", "absent-node-9999",
               "--config", config, "--graph-dir", graph_dir) == 2
    assert "is not a record node" in capsys.readouterr().err
    assert "epoch:" not in config.read_text()


def test_adopt_marker_appends_a_resolvable_epoch(tmp_path, capsys):
    repo = scratch_repo(tmp_path)
    config = repo / ".hypergraph" / "config.yml"
    graph_dir = repo / ".hypergraph" / "graph"
    run("adopt", "--repo", repo, "--init", "--config", config, "--graph-dir", graph_dir)
    root = next(iter(hg.load_local_nodes(graph_dir, "record")))
    body = tmp_path / "b.md"
    body.write_text("## What\n\nAdopted.\n")
    code, out = run_out(capsys, "new", "record", "--graph-dir", graph_dir,
                        "--title", "Adopted Hypergraph", "--body", body,
                        "--parent", root, "--none", "epoch marker")
    assert code == 0
    marker = out.split()[0]
    assert run("adopt", "--repo", repo, "--marker", marker, "--config", config,
               "--graph-dir", graph_dir) == 0
    assert f"marker: {marker}" in config.read_text()
    # one epoch per project — a second call must not append a rival block
    assert run("adopt", "--repo", repo, "--marker", marker, "--config", config,
               "--graph-dir", graph_dir) == 2
    assert config.read_text().count("epoch:") == 1
    capsys.readouterr()


def test_resolve_prefixes_maps_cited_id_prefixes_to_slugs(tmp_path):
    """Docs written before adoption cite raw id prefixes; the pointer currency is slugs."""
    repo = scratch_repo(tmp_path)
    export = tmp_path / "legacy.json"
    export.write_text(json.dumps({"nodes": [
        {"node_id": "b3ea0b95-1111-2222-3333-444444444444",
         "slug_name": "wise-anchor-1001", "title": "The one they cite"},
        {"node_id": "cccccccc-1111-2222-3333-444444444444",
         "slug_name": "brave-otter-1002", "title": "Another"}]}))
    (repo / "README.md").write_text(
        "The system of record is b3ea0b95. Unrelated sha: deadbeefcafe1234.\n")
    import subprocess as sp
    sp.run(["git", "add", "-A"], cwd=repo, check=True)
    sp.run(["git", "commit", "-qm", "docs"], cwd=repo, check=True)

    result = hg.resolve_id_prefixes(repo, export)
    resolved = {r["prefix"]: r["candidates"][0]["slug"] for r in result["resolved"]}
    assert resolved == {"b3ea0b95": "wise-anchor-1001"}
    assert result["ambiguous"] == []
    # a git sha resolves to nothing and is reported apart, not guessed at
    assert "deadbeefcafe1234" in result["unmatched_hex_tokens"]


def test_resolve_prefixes_reports_ambiguity_instead_of_guessing(tmp_path):
    repo = scratch_repo(tmp_path)
    export = tmp_path / "legacy.json"
    export.write_text(json.dumps({"nodes": [
        {"node_id": "abcd1234-1111-0000-0000-000000000001", "slug_name": "wise-anchor-1001"},
        {"node_id": "abcd1234-1111-0000-0000-000000000002", "slug_name": "brave-otter-1002"}]}))
    (repo / "README.md").write_text("See abcd1234 for the design.\n")
    import subprocess as sp
    sp.run(["git", "add", "-A"], cwd=repo, check=True)
    sp.run(["git", "commit", "-qm", "docs"], cwd=repo, check=True)
    result = hg.resolve_id_prefixes(repo, export)
    assert result["resolved"] == []
    assert len(result["ambiguous"]) == 1
    assert len(result["ambiguous"][0]["candidates"]) == 2


def test_adopt_with_no_mode_flag_says_what_it_does_and_does_not_do(tmp_path, capsys):
    assert run("adopt", "--repo", tmp_path) == 2
    err = capsys.readouterr().err
    assert "--survey" in err and "skill" in err


# ------------------------------------------------------- the documented order

def test_the_documented_mode_b_order_runs(tmp_path, capsys):
    """Walk hypergraph-adopt's mode-B steps as written, asserting exit 0 at each.

    The defect this guards: the skill used to author prehistory (step 2) before
    minting the roots (step 5), so an agent following it literally created a root
    to parent on and then `adopt --init` refused — `--force` included. Nothing in
    the suite noticed, because every test called `--init` on an empty graph."""
    repo = scratch_repo(tmp_path)
    config = repo / ".hypergraph" / "config.yml"
    graph_dir = repo / ".hypergraph" / "graph"
    cache = repo / ".hypergraph" / "cache"

    # 1. inventory  (2. read and 3. interview are the agent's, not the CLI's)
    assert run("adopt", "--repo", repo, "--survey") == 0

    # 4. init — before anything can be authored, because authoring needs a parent
    assert run("adopt", "--repo", repo, "--init", "--config", config,
               "--graph-dir", graph_dir) == 0
    record_root = next(iter(hg.load_local_nodes(graph_dir, "record")))
    state_root = next(iter(hg.load_local_nodes(graph_dir, "state")))

    # 5. prehistory — several nodes, one per era, each parented on the root
    body = tmp_path / "prehistory.md"
    body.write_text("## What\n\nAn era, honestly summarized.\n\n"
                    "## Evidence\n\nREADME.md; git log for the period.\n")
    prehistory = []
    for era in ("the script era", "the package era", "the service era"):
        code, out = run_out(capsys, "new", "record", "--graph-dir", graph_dir,
                            "--title", f"Prehistory: {era}", "--body", body,
                            "--parent", prehistory[-1] if prehistory else record_root,
                            "--impact", f"{state_root} — architecture distilled from the repo")
        assert code == 0
        prehistory.append(out.split()[0])

    # 6. epoch marker, parented on the newest prehistory node, then the epoch block
    marker_body = tmp_path / "marker.md"
    marker_body.write_text("## What\n\nAdopted Hypergraph: 3 prehistory nodes.\n")
    code, out = run_out(capsys, "new", "record", "--graph-dir", graph_dir,
                        "--title", "Adopted Hypergraph", "--body", marker_body,
                        "--parent", prehistory[-1], "--none", "epoch marker")
    assert code == 0
    marker = out.split()[0]
    assert run("adopt", "--repo", repo, "--marker", marker, "--config", config,
               "--graph-dir", graph_dir) == 0

    # 6, tail: advance the high-water mark to the marker
    code, sha = run_out(capsys, "update", state_root, "--graph-dir", graph_dir,
                        "--print-sha")
    assert code == 0
    state_body = tmp_path / "state-root.md"
    state_body.write_text(
        f"Distilled state graph root for {repo.name}.\n\n"
        f"## Reconciliation\n\n- high_water_mark: {marker}\n"
        "- reconciled_at: 2026-08-09T00:00:00+00:00\n")
    assert run("update", state_root, "--graph-dir", graph_dir, "--body", state_body,
               "--reconcile", "--expect", sha.strip()) == 0

    # 8, tail: export → check, exit 0 and nothing to report
    assert run("export", "--config", config, "--graph-dir", graph_dir,
               "--out-dir", cache) == 0
    assert run("check", "--record", cache / "record.json", "--state",
               cache / "state.json", "--config", config) == 0
    report = hg.run_check(cache / "record.json", cache / "state.json",
                          hg.load_config(config), config_given=True)
    assert report.violations() == [] and report.warnings() == []
    capsys.readouterr()


def test_init_adopts_a_hand_authored_record_root_instead_of_erroring(tmp_path, capsys):
    """Mode B from the other direction: prehistory was authored first."""
    repo = scratch_repo(tmp_path)
    config = repo / ".hypergraph" / "config.yml"
    graph_dir = repo / ".hypergraph" / "graph"
    body = tmp_path / "p.md"
    body.write_text("## What\n\nPrehistory, authored before the config existed.\n")
    code, out = run_out(capsys, "new", "record", "--graph-dir", graph_dir,
                        "--title", "Prehistory", "--body", body, "--root",
                        "--none", "pre-epoch history")
    assert code == 0
    authored = out.split()[0]

    code, out = run_out(capsys, "adopt", "--repo", repo, "--init", "--config", config,
                        "--graph-dir", graph_dir)
    assert code == 0
    assert f"record root: {authored} (adopted existing)" in out
    assert "state root:" in out and "(minted)" in out
    # the config points at the root that exists, not at a rival it minted beside it
    assert hg.load_config(config)["record_root"]["slug"] == authored
    assert len(hg.load_local_nodes(graph_dir, "record")) == 1


def test_init_adopts_the_imported_root_in_mode_a(tmp_path, capsys):
    """Mode A order: `import --fork` lands the legacy root, then `--init` runs.

    Minting a second root here would be the wrong answer twice over — the imported
    root *is* the graph's root, and two parentless roots fail I4."""
    repo = scratch_repo(tmp_path)
    config = repo / ".hypergraph" / "config.yml"
    graph_dir = repo / ".hypergraph" / "graph"
    assert run("import", "--record", CLEAN / "record.json", "--state",
               CLEAN / "state.json", "--graph-dir", graph_dir, "--fork") == 0
    roots = {kind: [s for s, n in hg.load_local_nodes(graph_dir, kind).items()
                    if not n.parents][0] for kind in ("record", "state")}

    code, out = run_out(capsys, "adopt", "--repo", repo, "--init", "--config", config,
                        "--graph-dir", graph_dir)
    assert code == 0
    assert f"record root: {roots['record']} (adopted existing)" in out
    assert f"state root:  {roots['state']} (adopted existing)" in out
    loaded = hg.load_config(config)
    assert loaded["record_root"]["slug"] == roots["record"]
    assert loaded["state_root"]["slug"] == roots["state"]
    # and the ids must be the *nodes'* own, not ones derived from their slugs
    for kind in ("record", "state"):
        node = hg.load_local_nodes(graph_dir, kind)[roots[kind]]
        assert loaded[f"{kind}_root"]["node_id"] == node.node_id


def test_init_writes_the_imported_roots_real_node_id_not_one_derived_from_the_slug(
        tmp_path, capsys):
    """`--fork` preserves the archive's node_id verbatim, so deriving the config's id
    from the slug wrote a config that disagreed with the node file it pointed at.
    `check` does not compare the two, and `mirror_root_ids()`/`push` read the config,
    so the graph would have published under an id nothing else in the repo used.

    Found on neural-whoop: the config claimed `8e92751d…`, the node file said
    `51aabea1…`, and the adopting agent had to hand-correct the YAML — the exact
    failure mode `--init` exists to prevent."""
    repo = scratch_repo(tmp_path)
    config = repo / ".hypergraph" / "config.yml"
    graph_dir = repo / ".hypergraph" / "graph"
    assert run("import", "--record", CLEAN / "record.json", "--state",
               CLEAN / "state.json", "--graph-dir", graph_dir, "--fork") == 0

    # give the record root an id that is deliberately not uuid5(slug), as a real
    # archive id would be
    slug = [s for s, n in hg.load_local_nodes(graph_dir, "record").items()
            if not n.parents][0]
    path = graph_dir / "record" / f"{slug}.md"
    archive_id = "51aabea1-f793-534d-a0a7-bc9b1e368bbb"
    meta, _ = hg.split_frontmatter(path.read_text())
    path.write_text(path.read_text().replace(meta["node_id"], archive_id))

    assert run("adopt", "--repo", repo, "--init", "--config", config,
               "--graph-dir", graph_dir) == 0
    capsys.readouterr()
    assert hg.load_config(config)["record_root"]["node_id"] == archive_id
    assert archive_id != hg.node_id_for(slug)


def duplicate_root(graph_dir, kind, slug, new_slug):
    """A second parentless root of the same kind — an ambiguity, hand-made."""
    src = graph_dir / kind / f"{slug}.md"
    text = src.read_text().replace(slug, new_slug)
    meta, _body = hg.split_frontmatter(text)
    text = text.replace(meta["node_id"], hg.node_id_for(new_slug))
    (graph_dir / kind / f"{new_slug}.md").write_text(text)


def test_init_refuses_to_choose_between_two_parentless_roots(tmp_path, capsys):
    repo = scratch_repo(tmp_path)
    config = repo / ".hypergraph" / "config.yml"
    graph_dir = repo / ".hypergraph" / "graph"
    body = tmp_path / "p.md"
    body.write_text("## What\n\nPrehistory.\n")
    code, out = run_out(capsys, "new", "record", "--graph-dir", graph_dir,
                        "--title", "Prehistory", "--body", body, "--root",
                        "--none", "pre-epoch history")
    assert code == 0
    first = out.split()[0]
    duplicate_root(graph_dir, "record", first, "rival-root-9999")

    assert run("adopt", "--repo", repo, "--init", "--config", config,
               "--graph-dir", graph_dir) == 2
    err = capsys.readouterr().err
    assert first in err and "rival-root-9999" in err   # names both, picks neither
    assert not config.exists()


# ----------------------------------------------------------- timeline signals

def test_survey_reports_tags_and_directory_births(tmp_path):
    """The signals an adopter's epoch boundary actually falls on.

    `ERA_GAP_DAYS` found one era spanning all 347 commits of a real repo; directory
    births found four boundaries in the same history."""
    repo = scratch_repo(tmp_path)
    sp = subprocess.run
    sp(["git", "tag", "-a", "v0.1.0", "-m", "first release"], cwd=repo, check=True)
    (repo / "dashboard").mkdir()
    (repo / "dashboard" / "app.py").write_text("app = 1\n")
    sp(["git", "add", "-A"], cwd=repo, check=True)
    sp(["git", "commit", "-qm", "dashboard"], cwd=repo, check=True)

    git = hg.adopt_survey(repo)["git"]
    assert [t["tag"] for t in git["tags"]] == ["v0.1.0"]
    assert git["tags"][0]["date"]
    births = {b["path"]: b["date"] for b in git["dir_births"]}
    # `tests/` exists on disk but no commit touches it — a dir git never saw has no
    # birth, and reporting one would be a boundary the author cannot recognize.
    assert set(births) == {"src", "dashboard"}
    assert births["src"] and births["dashboard"]


def test_survey_says_none_rather_than_going_quiet(tmp_path, capsys):
    """Most repos have no tags. That is an empty list, never a warning — but it must
    still be *said*.

    Printing only the categories that fired left a reader unable to tell "no tags in
    this repo" from "tags were not computed": one adoption reported the survey
    "prints one signal category and stays silent about the others", and had to read
    `--survey --json` to learn the other two were empty rather than unimplemented. A
    silent category reads as an absent feature."""
    repo = scratch_repo(tmp_path)
    git = hg.adopt_survey(repo)["git"]
    assert git["tags"] == []
    assert [b["path"] for b in git["dir_births"]] == ["src"]

    assert run("adopt", "--repo", repo, "--survey") == 0
    cap = capsys.readouterr()
    assert cap.err == ""
    assert "tags — none in this repo" in cap.out
    assert "directory births" in cap.out
    assert "quiet gaps — none longer than" in cap.out
    assert "one continuous era" in cap.out


# ------------------------------------------------------------------- the docs

def test_readme_names_the_pypi_install_path():
    """The front door went stale once: Quickstart opened with `./install.sh`, which
    needs a clone of this repo — and adopters never clone it."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "uv tool install hypergraph-protocol" in readme
    assert "hypergraph skills install" in readme
    install = readme.index("## Install")
    assert install < readme.index("## Quickstart")
    # the dev-checkout form belongs below, not in the adopter's first screen
    assert install < readme.index("./install.sh")
