"""Upgrading an adopted repo's copies, and detecting when nobody did.

An adopted repo carries *copies* of what this package ships — the five skills, the
sentinel-delimited AGENTS.md block, sometimes the CI workflows. `uv tool upgrade`
refreshes the CLI and cannot see any of them. That gap shipped: 0.0.6 fixed the
adopt workflow, and every repo that had already run `skills install` kept the
installed skill describing the step order 0.0.6 fixed, with nothing anywhere to say
so.

Two properties carry the weight here:

- **upgrade never installs what is not already there.** An upgrade that quietly adds
  CI to a repo that never wanted it is worse than a stale file — and it is what
  keeps the command from writing outside the repo it was pointed at.
- **the skew is *detected*, not assumed.** The stamp exists so `check` can say which
  half is old; without it the staleness is invisible, which is exactly how it got
  shipped.
"""
import subprocess
from pathlib import Path

from graph_fixtures import hg

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skills"

# The block exactly as 0.0.6 shipped it. An adopter who never edited theirs has
# this in their AGENTS.md, and upgrade may replace it because we can prove we
# wrote every byte — its digest is in `SHIPPED_BLOCK_DIGESTS`. Kept verbatim here
# rather than read out of git history, so the test states the contract instead of
# depending on the repository it runs in.
BLOCK_0_0_6 = """<!-- hypergraph:begin -->
## Hypergraph protocol

This repo's memory lives in two graphs under `.hypergraph/` (see `.hypergraph/AGENTS.md`):

1. **Orient on arrival**: run the `hypergraph-orient` skill or read `STATE.md` —
   the frontier (open/broken/blocked) is what matters now.
2. **Record every unit of work** (features, fixes, experiments, dead ends,
   decisions): the `hypergraph-record` skill — one causally-parented record node
   with a `## State Impact` section. Unrecorded work is invisible to the project.
3. **Never write state nodes**; declare impacts and let the
   `hypergraph-reconcile` skill fold them. `STATE.md` is generated — never
   hand-edit it.
4. **Verify before finishing**: `hypergraph export` + `hypergraph check` must
   exit 0.
<!-- hypergraph:end -->"""


def run(*argv):
    return hg.main([str(a) for a in argv])


def run_out(capsys, *argv):
    capsys.readouterr()
    code = run(*argv)
    return code, capsys.readouterr().out


def adopted_repo(tmp_path, *, skills=True, agents=True, workflow=True, config=True,
                 block=BLOCK_0_0_6):
    """A repo shaped like one that ran adopt some releases ago.

    `block` defaults to a genuinely-shipped older template, because that is the
    only shape upgrade may overwrite; pass an edited one to exercise the case
    where it must step back."""
    repo = tmp_path / "adopted"
    (repo / ".hypergraph").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    if skills:
        target = repo / ".claude" / "skills"
        target.mkdir(parents=True)
        for src in sorted(SOURCE.glob("hypergraph-*")):
            dst = target / src.name
            dst.mkdir()
            # a stale snapshot: one file, wrong content — not the current tree
            (dst / "SKILL.md").write_text("---\nname: stale\n---\n\nOld instructions.\n")
    if agents:
        (repo / "AGENTS.md").write_text(
            "# My project\n\nOur own rules.\n\n"
            f"{block}\n\nMore of our prose.\n")
    if workflow:
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "hypergraph-check.yml").write_text(
            (ROOT / "templates" / "github-actions" / "hypergraph-check.yml").read_text())
    if config:
        (repo / ".hypergraph" / "config.yml").write_text(
            "# config\nproject: adopted\n\nrecord_root:\n  slug: wise-anchor-1001\n")
    return repo


# ------------------------------------------------------------------- refreshing

def test_upgrade_refreshes_stale_skills_and_prunes_removed_files(tmp_path, capsys):
    """`skills install` merges (dirs_exist_ok), so a file dropped upstream would
    linger forever. Upgrade replaces the tree, which is the one safe place to."""
    repo = adopted_repo(tmp_path)
    stray = repo / ".claude" / "skills" / "hypergraph-adopt" / "REMOVED-UPSTREAM.md"
    stray.write_text("gone in a later release\n")

    assert run("upgrade", "--repo", repo) == 0
    capsys.readouterr()
    installed = (repo / ".claude" / "skills" / "hypergraph-adopt" / "SKILL.md").read_text()
    assert installed == (SOURCE / "hypergraph-adopt" / "SKILL.md").read_text()
    assert not stray.exists()


def test_upgrade_never_installs_what_is_not_already_there(tmp_path, capsys):
    """The whole safety property: upgrade refreshes copies, it does not adopt."""
    repo = adopted_repo(tmp_path, skills=False, agents=False, workflow=False)
    assert run("upgrade", "--repo", repo) == 0
    capsys.readouterr()
    assert not (repo / ".claude").exists()
    assert not (repo / "AGENTS.md").exists()
    assert not (repo / ".github").exists()


def test_upgrade_replaces_an_unedited_block_and_leaves_the_prose_alone(tmp_path, capsys):
    repo = adopted_repo(tmp_path)
    assert run("upgrade", "--repo", repo) == 0
    capsys.readouterr()
    text = (repo / "AGENTS.md").read_text()
    assert "hypergraph export` + `hypergraph check` must\n   exit 0.\n<!--" not in text
    assert (ROOT / "templates" / "agents-block.md").read_text().strip() in text
    # everything outside the sentinels is the adopter's, and survives verbatim
    assert text.startswith("# My project\n\nOur own rules.\n")
    assert text.endswith("More of our prose.\n")


# ------------------------------------------------- the block adopt writes into
#
# The sentinels do not mean "ours to overwrite". hypergraph-adopt's step 8 writes
# per-project content *inside* them — the contract reconciliation that routes an
# existing discipline through hypergraph, and the project's epoch note — and 0.0.7
# replaced the lot with the shipped template, silently. Found on cadex, whose block
# lost the clause telling agents that `docs/DECISIONS.md` is not superseded.

def edited_block() -> str:
    """A shipped block with the two things adopt actually adds to one."""
    return BLOCK_0_0_6.replace(
        "with a `## State Impact` section. Unrecorded work is invisible to the project.",
        "with a `## State Impact` section. Unrecorded work is invisible to the project.\n"
        "   This **complements** `docs/DECISIONS.md` rather than replacing it.",
    ).replace(
        "<!-- hypergraph:end -->",
        "\nThe epoch marker is `winter-rain-7897`; the 14 nodes before it are"
        " prehistory.\n<!-- hypergraph:end -->")


def test_upgrade_does_not_overwrite_a_block_the_adopter_edited(tmp_path, capsys):
    """The regression. Both additions are the adopt skill's own output."""
    repo = adopted_repo(tmp_path, block=edited_block())
    before = (repo / "AGENTS.md").read_text()

    code, out = run_out(capsys, "upgrade", "--repo", repo)

    assert code == 0
    assert (repo / "AGENTS.md").read_text() == before
    assert "customized" in out
    assert "--agents-block" in out
    assert "docs/DECISIONS.md" in (repo / "AGENTS.md").read_text()


def test_upgrade_overwrites_an_edited_block_only_when_asked(tmp_path, capsys):
    repo = adopted_repo(tmp_path, block=edited_block())
    assert run("upgrade", "--repo", repo, "--agents-block") == 0
    out = capsys.readouterr().out
    text = (repo / "AGENTS.md").read_text()
    assert "docs/DECISIONS.md" not in text
    assert (ROOT / "templates" / "agents-block.md").read_text().strip() in text
    assert "overwrote local edits" in out
    # and the adopter's prose outside the sentinels is still not ours to touch
    assert text.startswith("# My project\n\nOur own rules.\n")


def test_upgrade_names_the_shipped_block_so_the_adopter_can_merge(tmp_path, capsys):
    """Reporting drift is only half a remedy; the other half is saying what to
    compare against."""
    repo = adopted_repo(tmp_path, block=edited_block())
    _code, out = run_out(capsys, "upgrade", "--repo", repo)
    assert "agents-block.md" in out
    assert "left alone" in out


def test_upgrade_is_idempotent_on_a_block_it_just_wrote(tmp_path, capsys):
    """The block upgrade writes is a shipped one, so the next run reports it
    unchanged rather than rediscovering it as an edit."""
    repo = adopted_repo(tmp_path)
    run("upgrade", "--repo", repo)
    _code, out = run_out(capsys, "upgrade", "--repo", repo)
    assert "customized" not in out
    assert "unchanged" in out


def test_shipped_block_digest_is_registered(tmp_path):
    """The set is hand-maintained, so it needs a tripwire: change the template
    without adding its digest and every adopter's next upgrade reports their
    untouched block as customized."""
    current = (ROOT / "templates" / "agents-block.md").read_text()
    assert hg.block_digest(current) in hg.SHIPPED_BLOCK_DIGESTS
    assert hg.block_digest(BLOCK_0_0_6) in hg.SHIPPED_BLOCK_DIGESTS


def test_upgrade_writes_through_a_claude_md_symlink_without_breaking_it(tmp_path, capsys):
    """adopt has warned about this rule in prose since it shipped. Here it holds
    because `write_text` follows the link — and the target is edited exactly once."""
    repo = adopted_repo(tmp_path)
    (repo / "CLAUDE.md").symlink_to("AGENTS.md")
    assert run("upgrade", "--repo", repo) == 0
    out = capsys.readouterr().out
    assert (repo / "CLAUDE.md").is_symlink()
    assert (repo / "CLAUDE.md").readlink() == Path("AGENTS.md")
    assert (repo / "AGENTS.md").read_text().count(hg.AGENTS_BEGIN) == 1
    assert out.count("AGENTS.md") == 1          # one file, reported once


def test_upgrade_leaves_a_file_that_never_had_a_block(tmp_path, capsys):
    repo = adopted_repo(tmp_path, agents=False)
    (repo / "AGENTS.md").write_text("# Ours alone\n\nNo hypergraph block here.\n")
    assert run("upgrade", "--repo", repo) == 0
    capsys.readouterr()
    assert (repo / "AGENTS.md").read_text() == "# Ours alone\n\nNo hypergraph block here.\n"


# -------------------------------------------------------------------- workflows

def test_upgrade_reports_a_drifted_workflow_but_does_not_touch_it(tmp_path, capsys):
    """Workflows are the copied artifact adopters genuinely edit. Overwriting them
    by default would make `upgrade` unrunnable without reading the diff first."""
    repo = adopted_repo(tmp_path)
    wf = repo / ".github" / "workflows" / "hypergraph-check.yml"
    wf.write_text(wf.read_text() + "\n# our own extra step\n")
    before = wf.read_text()

    code, out = run_out(capsys, "upgrade", "--repo", repo)
    assert code == 0
    assert "differs" in out and "--workflows" in out
    assert wf.read_text() == before

    assert run("upgrade", "--repo", repo, "--workflows") == 0
    capsys.readouterr()
    assert wf.read_text() == (
        ROOT / "templates" / "github-actions" / "hypergraph-check.yml").read_text()


# ---------------------------------------------------------------- config + safety

def test_upgrade_stamps_the_version_and_is_idempotent(tmp_path, capsys):
    repo = adopted_repo(tmp_path)
    config = repo / ".hypergraph" / "config.yml"
    assert run("upgrade", "--repo", repo) == 0
    capsys.readouterr()
    text = config.read_text()
    assert f"hypergraph_version: {hg.__version__}" in text
    assert "project: adopted" in text and "slug: wise-anchor-1001" in text

    code, out = run_out(capsys, "upgrade", "--repo", repo)
    assert code == 0
    assert "already current" in out
    assert config.read_text() == text          # a second run changes nothing


def test_upgrade_dry_run_writes_nothing(tmp_path, capsys):
    repo = adopted_repo(tmp_path)
    skill = repo / ".claude" / "skills" / "hypergraph-adopt" / "SKILL.md"
    before = (skill.read_text(), (repo / "AGENTS.md").read_text(),
              (repo / ".hypergraph" / "config.yml").read_text())

    code, out = run_out(capsys, "upgrade", "--repo", repo, "--dry-run")
    assert code == 0
    assert "would refresh" in out
    assert (skill.read_text(), (repo / "AGENTS.md").read_text(),
            (repo / ".hypergraph" / "config.yml").read_text()) == before


def test_upgrade_refuses_to_run_in_the_protocols_own_checkout(tmp_path, capsys):
    """Here the skills are dogfooding symlinks into `skills/` and the publish
    workflow deliberately differs from the template. Refreshing either from the
    package would overwrite the source with a copy of itself."""
    assert run("upgrade", "--repo", ROOT) == 2
    err = capsys.readouterr().err
    assert "own checkout" in err and "symlink" in err


def test_adopt_init_stamps_the_version(tmp_path, capsys):
    repo = tmp_path / "fresh"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    config = repo / ".hypergraph" / "config.yml"
    assert run("adopt", "--repo", repo, "--init", "--config", config,
               "--graph-dir", repo / ".hypergraph" / "graph") == 0
    capsys.readouterr()
    assert f"hypergraph_version: {hg.__version__}" in config.read_text()


# ------------------------------------------------------------------ skew in check

def skew(declared):
    report = hg.Report()
    config = {} if declared is None else {"hypergraph_version": declared}
    hg.check_version_skew(config, report)
    return report


def test_check_warns_when_the_repos_copies_are_behind_the_cli():
    findings = skew("0.0.1").warnings()
    assert len(findings) == 1
    text = str(findings[0])
    assert "hypergraph upgrade" in text
    # the distinction that keeps this from reading as a data-format problem
    assert "node files are fine" in text


def test_check_warns_the_other_way_when_the_cli_is_the_old_half():
    findings = skew("99.0.0").warnings()
    assert len(findings) == 1
    assert "uv tool upgrade hypergraph-protocol" in str(findings[0])


def test_matching_versions_and_unparseable_ones_say_nothing():
    assert skew(hg.__version__).warnings() == []
    assert skew(hg.__version__).infos() == []
    # a dev/pre-release string is not orderable — never guess at a direction
    assert skew("1.2.0rc1").warnings() == []


def test_a_missing_stamp_is_an_info_not_a_warning():
    """Every repo adopted before the stamp existed lacks it. That is normal, so it
    must not colour anyone's checker output — but it is worth saying once."""
    report = skew(None)
    assert report.warnings() == []
    assert len(report.infos()) == 1
    assert "hypergraph upgrade" in str(report.infos()[0])


def test_version_skew_never_fails_a_build(tmp_path, capsys):
    """A warning, by construction: `check` exits nonzero only on violations, and
    failing someone's CI because their skill files are a release behind is hostile."""
    import json
    from graph_fixtures import CLEAN
    roots = {kind: next(n for n in json.loads((CLEAN / f"{kind}.json").read_text())["nodes"]
                        if not n.get("parent_ids"))["slug_name"]
             for kind in ("record", "state")}
    config = tmp_path / "config.yml"
    config.write_text(f"project: clean\nrecord_root:\n  slug: {roots['record']}\n"
                      f"state_root:\n  slug: {roots['state']}\n"
                      "hypergraph_version: 0.0.1\n")
    code, out = run_out(capsys, "check", "--record", CLEAN / "record.json",
                        "--state", CLEAN / "state.json", "--config", config)
    assert code == 0
    assert "hypergraph upgrade" in out
