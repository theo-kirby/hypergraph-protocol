"""The distribution is an allow-list — assert nothing local can sneak into it.

Both hatchling targets are allow-lists today (`force-include` for the wheel,
`include` for the sdist), which makes the exclusion automatic. These tests exist
so that a future edit adding a broad glob, or dropping the sdist's explicit
`include`, fails here instead of on PyPI.

`research/` used to live here and is named below out of caution rather than
presence: the benchmark lab moved to the private `hypergraph-labs` repo on
2026-08-11, so a `research/` reappearing in this tree would be something new and
undeclared rather than the lab. `tests/` and `.hypergraph/` are the live cases —
an end user installing the CLI has no use for this repo's own test suite or its
memory graphs.
"""
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Directories that must never be distributed, whether or not they exist here.
NEVER_SHIP = ("research", "tests", ".hypergraph")


def _pyproject():
    with (ROOT / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)


def test_wheel_force_include_is_an_explicit_allow_list():
    """The wheel ships only what force-include names — and never research/."""
    cfg = _pyproject()["tool"]["hatch"]["build"]["targets"]["wheel"]
    # An allow-list is the whole safety property: if `force-include` were ever
    # replaced by a `packages`/`include` glob over the repo root, this fails.
    assert "force-include" in cfg, "wheel target must stay an explicit allow-list"
    for src in cfg["force-include"]:
        top = Path(src).parts[0]
        assert top not in NEVER_SHIP, f"wheel would ship {src}"


def test_sdist_include_is_an_explicit_allow_list():
    """The sdist ships only what `include` names — and never research/."""
    cfg = _pyproject()["tool"]["hatch"]["build"]["targets"]["sdist"]
    assert "include" in cfg, "sdist target must stay an explicit allow-list"
    for src in cfg["include"]:
        top = Path(src).parts[0]
        assert top not in NEVER_SHIP, f"sdist would ship {src}"


def test_the_allow_lists_are_not_vacuous():
    """Guard the guard.

    The two assertions above iterate the declared sources and check none of them
    starts with a NEVER_SHIP directory. That is trivially true of an empty list,
    so this pins that the lists have real content and that the live exclusions —
    `tests/` and `.hypergraph/` — are directories that actually exist here.
    Without it, deleting every `force-include` entry would leave a green suite.
    """
    cfg = _pyproject()["tool"]["hatch"]["build"]["targets"]
    assert cfg["wheel"]["force-include"], "wheel allow-list is empty"
    assert cfg["sdist"]["include"], "sdist allow-list is empty"
    for present in ("tests", ".hypergraph"):
        assert (ROOT / present).is_dir(), f"{present}/ vanished; its exclusion is now vacuous"


def test_module_version_matches_pyproject():
    """`hypergraph --version` must not disagree with the distribution.

    The benchmark's arm-C boxes install `hypergraph-protocol==<version>` and then
    assert the version the CLI reports, because `uv tool install` reuses a cached
    tool and would otherwise leave a box silently running an older build while
    the write-up names this one. That assertion is only meaningful if the two
    numbers are the same number here.
    """
    import re
    declared = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    source = (ROOT / "tools" / "hypergraph.py").read_text(encoding="utf-8")
    in_module = re.search(r'^__version__ = "([^"]+)"', source, re.M)
    assert in_module, "tools/hypergraph.py declares no __version__"
    assert in_module.group(1) == declared, (
        f"tools/hypergraph.py says {in_module.group(1)}, pyproject says {declared}")


def test_spec_header_matches_pyproject():
    """SPEC.md's version header must not drift from the distribution.

    It did: the spec said v0.0.2 while the tool shipped 0.0.3, so the document
    describing the protocol disagreed with the artifact implementing it. Four lines
    closes that permanently — SPEC.md is the durable publication artifact, and a
    wrong version number on it is a claim about which protocol you are reading.
    """
    import re
    declared = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    header = (ROOT / "SPEC.md").read_text(encoding="utf-8").splitlines()[0]
    found = re.search(r"v(\d+\.\d+\.\d+)", header)
    assert found, f"SPEC.md's first line carries no version: {header!r}"
    assert found.group(1) == declared, (
        f"SPEC.md says v{found.group(1)}, pyproject says {declared}")


def test_sdist_actually_contains_the_skills_tree(tmp_path):
    """Build the sdist and look inside it. The static assertions above cannot see this.

    `.claude/skills/hypergraph-*` are committed symlinks into `skills/`, and hatchling
    walks with `followlinks=True` while skipping any directory whose `(st_dev, st_ino)`
    it has already seen. So it materialized the skills under `.claude/` and then dropped
    the real `skills/` as a duplicate — an sdist with no `skills/` at all, whose wheel
    build fails on the force-include of it. Every declaration in pyproject was correct;
    only the built artifact was wrong, which is why this test builds one.

    `exclude` alone does not fix it: it filters the output, not the walk. The fix is
    `skip-excluded-dirs = true`, and this test is what keeps it there.
    """
    import shutil
    import subprocess
    import tarfile

    if shutil.which("uv") is None:
        import pytest
        pytest.skip("uv is not on PATH")

    proc = subprocess.run(["uv", "build", "--sdist", "--out-dir", str(tmp_path)],
                          cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, f"sdist build failed:\n{proc.stderr}"

    sdists = list(tmp_path.glob("*.tar.gz"))
    assert len(sdists) == 1, f"expected one sdist, got {sdists}"
    with tarfile.open(sdists[0]) as tar:
        names = ["/".join(n.split("/")[1:]) for n in tar.getnames()]

    for src in _pyproject()["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]:
        assert any(n == src or n.startswith(src.rstrip("/") + "/") for n in names), (
            f"the wheel force-includes {src!r}, but the sdist does not carry it — "
            "building a wheel from this sdist would fail")

    for never in NEVER_SHIP:
        assert not any(n.split("/")[0] == never for n in names), f"sdist ships {never}/"
    assert not any(n.split("/")[0] == ".claude" for n in names), (
        "sdist ships the .claude symlink tree, which shadows skills/ during the walk")


def test_this_repos_config_stamp_matches_pyproject():
    """The dogfood config's `hypergraph_version:` must not drift either.

    In this repo the stamp is always true by construction — `.claude/skills/*` are
    symlinks into `skills/`, so there are no copies to go stale, which is why
    `hypergraph upgrade` refuses to run here. That is exactly what makes it easy to
    forget on a release, and a wrong stamp makes `check` tell every reader of this
    repo to run an upgrade that would do nothing.
    """
    import re
    declared = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    config = (ROOT / ".hypergraph" / "config.yml").read_text(encoding="utf-8")
    found = re.search(r"^hypergraph_version:\s*(\S+)$", config, flags=re.M)
    assert found, ".hypergraph/config.yml carries no hypergraph_version:"
    assert found.group(1) == declared, (
        f"config says {found.group(1)}, pyproject says {declared}")


def test_templates_config_stamp_matches_pyproject():
    """hypergraph-init writes a config by hand from this template, so a stale
    version here is copied verbatim into every new project it initializes."""
    import re
    declared = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    template = (ROOT / "templates" / "config.example.yml").read_text(encoding="utf-8")
    found = re.search(r"^hypergraph_version:\s*(\S+)$", template, flags=re.M)
    assert found, "templates/config.example.yml carries no hypergraph_version:"
    assert found.group(1) == declared, (
        f"template says {found.group(1)}, pyproject says {declared}")


# ---- the shared references payload (0.1.0 gate, U6) ---------------------------

import yaml

from graph_fixtures import hg


def test_wheel_force_include_enumerates_every_skill_file():
    """force-include bypasses every exclude filter, so the skill payload is
    enumerated file by file. A new skill (or a second file in one) must land
    here, loudly, or it silently never ships."""
    sources = set(_pyproject()["tool"]["hatch"]["build"]["targets"]["wheel"]
                  ["force-include"])
    expected = {str(p.relative_to(ROOT))
                for p in (ROOT / "skills").rglob("*")
                if p.is_file() and not p.name.startswith(".")
                and "references" not in p.relative_to(ROOT).parts}
    missing = expected - sources
    assert not missing, f"skill files the wheel would not ship: {sorted(missing)}"


def test_manifest_matches_the_dogfooding_symlinks():
    """skills/references.yml is the wheel's stand-in for the symlinks a wheel
    cannot carry. Two representations of one fact — this pins them equal."""
    from_symlinks = hg.skill_reference_sets(ROOT / "skills")
    manifest = {str(k): sorted(str(n) for n in v) for k, v in
                yaml.safe_load((ROOT / "skills" / "references.yml").read_text()).items()}
    assert from_symlinks == manifest


def test_every_manifest_reference_ships_in_the_shared_payload():
    """Each name a skill links to must exist once under references/ in the wheel."""
    force = _pyproject()["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    shipped = {Path(dest).name for dest in force.values()
               if dest.startswith("hypergraph_protocol_data/references/")}
    for skill, names in hg.skill_reference_sets(ROOT / "skills").items():
        missing = set(names) - shipped
        assert not missing, f"{skill} references {sorted(missing)} — not in the wheel payload"


def test_wheel_ships_each_reference_exactly_once(tmp_path):
    """Build the wheel and look inside: one spec.md, no per-skill copies."""
    import shutil
    import subprocess
    import zipfile

    if shutil.which("uv") is None:
        import pytest
        pytest.skip("uv is not on PATH")
    proc = subprocess.run(["uv", "build", "--wheel", "--out-dir", str(tmp_path)],
                          cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, f"wheel build failed:\n{proc.stderr}"
    wheel = next(tmp_path.glob("*.whl"))
    names = zipfile.ZipFile(wheel).namelist()
    spec_copies = [n for n in names if n.endswith("spec.md")]
    assert spec_copies == ["hypergraph_protocol_data/references/spec.md"]
    assert not any("skills/hypergraph" in n and "/references/" in n for n in names)
    assert "hypergraph_protocol_data/skills/references.yml" in names


def _fake_wheel_root(tmp_path):
    """The installed-wheel layout: skills without references, plus the payload."""
    root = tmp_path / "wheel-data"
    for skill, names in hg.skill_reference_sets(ROOT / "skills").items():
        sdir = root / "skills" / skill
        sdir.mkdir(parents=True)
        (sdir / "SKILL.md").write_text((ROOT / "skills" / skill / "SKILL.md").read_text())
    (root / "skills" / "references.yml").write_text(
        (ROOT / "skills" / "references.yml").read_text())
    refs = root / "references"
    refs.mkdir()
    all_names = {n for names in hg.skill_reference_sets(ROOT / "skills").values()
                 for n in names}
    for name in sorted(all_names):
        source = {"spec.md": ROOT / "SPEC.md",
                  "local-adapter.md": ROOT / "backend" / "local-adapter.md",
                  "lanes.md": ROOT / "backend" / "lanes.md"}.get(
                      name, ROOT / "templates" / name)
        (refs / name).write_text(source.read_text())
    (root / "templates").mkdir()
    (root / "templates" / "agents-block.md").write_text(
        (ROOT / "templates" / "agents-block.md").read_text())
    return root


def test_wheel_layout_install_links_references_that_resolve(tmp_path, monkeypatch):
    root = _fake_wheel_root(tmp_path)
    monkeypatch.setattr(hg, "skills_data_root", lambda: root)
    target = tmp_path / "claude-skills"
    assert hg.main(["skills", "install", "--target", str(target)]) == 0
    assert (target / "hypergraph-references" / "spec.md").is_file()
    for skill, names in hg.skill_reference_sets(ROOT / "skills").items():
        for name in names:
            link = target / skill / "references" / name
            assert link.is_symlink(), f"{link} is not a symlink"
            assert link.resolve() == (target / "hypergraph-references" / name).resolve()
            assert link.read_text()  # and it resolves to real content
    # each referenced file's bytes exist exactly once under the target
    spec_files = [p for p in target.rglob("spec.md") if p.is_file() and not p.is_symlink()]
    assert spec_files == [target / "hypergraph-references" / "spec.md"]


def test_wheel_layout_refuses_link_mode(tmp_path, monkeypatch, capsys):
    root = _fake_wheel_root(tmp_path)
    monkeypatch.setattr(hg, "skills_data_root", lambda: root)
    assert hg.main(["skills", "install", "--link",
                    "--target", str(tmp_path / "t")]) == 2
    assert "dev checkout" in capsys.readouterr().err


def test_upgrade_converts_a_fat_install_to_shared_references(tmp_path, monkeypatch):
    """A pre-0.1.0 install holds six full copies; its first upgrade prunes them
    into links against the freshly written shared payload."""
    import subprocess
    root = _fake_wheel_root(tmp_path)
    monkeypatch.setattr(hg, "skills_data_root", lambda: root)
    repo = tmp_path / "adopted"
    (repo / ".hypergraph").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    target = repo / ".claude" / "skills"
    for skill, names in hg.skill_reference_sets(ROOT / "skills").items():
        refs = target / skill / "references"
        refs.mkdir(parents=True)
        (target / skill / "SKILL.md").write_text("old\n")
        for name in names:
            (refs / name).write_text("stale fat copy\n")
    assert hg.main(["upgrade", "--repo", str(repo)]) == 0
    assert (target / "hypergraph-references" / "spec.md").is_file()
    link = target / "hypergraph-record" / "references" / "spec.md"
    assert link.is_symlink()
    assert link.read_text() == (ROOT / "SPEC.md").read_text()
