"""Checker tests over committed fixtures: clean passes, each seeded violation is caught."""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tools" / "fixtures"

_spec = importlib.util.spec_from_file_location("hypergraph", ROOT / "tools" / "hypergraph.py")
hg = importlib.util.module_from_spec(_spec)
sys.modules["hypergraph"] = hg
_spec.loader.exec_module(hg)

VIOLATION_DIRS = sorted(p for p in (FIXTURES / "violations").iterdir() if p.is_dir())


def check(fixture_dir):
    # A fixture that needs a config (a seeded named-view violation, say) commits
    # one as config.json beside its exports; every other fixture runs config-less.
    config = None
    config_path = fixture_dir / "config.json"
    if config_path.exists():
        import json
        config = json.loads(config_path.read_text())
    return hg.run_check(fixture_dir / "record.json", fixture_dir / "state.json", config)


def test_clean_fixture_passes():
    report = check(FIXTURES / "clean")
    assert report.violations() == []
    assert report.warnings() == []


def test_clean_fixture_reports_zero_unreconciled():
    report = check(FIXTURES / "clean")
    unrec = [f for f in report.infos() if "unreconciled" in f.message]
    assert len(unrec) == 1
    assert unrec[0].message.startswith("0 unreconciled")


@pytest.mark.parametrize("fixture_dir", VIOLATION_DIRS, ids=lambda p: p.name)
def test_violation_fixture_fails_with_right_invariant(fixture_dir):
    expected = fixture_dir.name.split("-")[0].upper()  # i2-missing-impact -> I2
    report = check(fixture_dir)
    violations = report.violations()
    assert violations, f"{fixture_dir.name}: expected at least one violation"
    assert {f.invariant for f in violations} == {expected}, (
        f"{fixture_dir.name}: expected only {expected} violations, "
        f"got {[(f.invariant, f.message) for f in violations]}"
    )


def test_all_seeded_invariants_covered():
    assert {p.name.split("-")[0].upper() for p in VIOLATION_DIRS} == {"I2", "I4", "I5", "I6", "I7"}


def test_check_cli_exit_codes(capsys):
    clean = FIXTURES / "clean"
    bad = FIXTURES / "violations" / "i6-bad-status"
    assert hg.main(["check", "--record", str(clean / "record.json"),
                    "--state", str(clean / "state.json")]) == 0
    assert hg.main(["check", "--record", str(bad / "record.json"),
                    "--state", str(bad / "state.json")]) == 1
    out = capsys.readouterr().out
    assert "VIOLATION I6" in out


def test_render_frontier_and_tree(tmp_path):
    out = hg.render_state(FIXTURES / "clean" / "state.json")
    assert "## Frontier" in out
    assert "[open]" in out and "Query API" in out          # frontier node
    assert "Ingest pipeline" in out and "[working]" in out  # architecture tree
    assert "Reconciled through `dim-walrus-0004`" in out
    # working nodes stay out of the frontier section
    frontier_section = out.split("## Frontier")[1].split("## Architecture")[0]
    assert "Ingest pipeline" not in frontier_section


EPOCH = FIXTURES / "epoch"
EPOCH_CONFIG = {"epoch": {"marker": "bright-gate-0003"}}


def test_epoch_legacy_node_exempt_from_i2():
    report = hg.run_check(EPOCH / "record.json", EPOCH / "state.json", EPOCH_CONFIG)
    assert report.violations() == []
    exempt = [f for f in report.infos() if "pre-epoch" in f.message]
    assert len(exempt) == 1 and exempt[0].message.startswith("1 pre-epoch")


def test_epoch_only_shields_legacy_nodes():
    """Without the epoch config, the same legacy node is an I2 violation."""
    report = hg.run_check(EPOCH / "record.json", EPOCH / "state.json")
    assert [f.node for f in report.violations()] == ["faded-scroll-0002"]
    assert all(f.invariant == "I2" for f in report.violations())


def test_epoch_post_epoch_node_still_fails_i2(tmp_path):
    """A node created after the marker gets no exemption."""
    import json
    graph = json.loads((EPOCH / "record.json").read_text())
    graph["nodes"].append({
        "node_id": "20000000-0000-0000-0000-000000000004",
        "slug_name": "loud-comet-0004",
        "title": "Post-epoch work without an impact",
        "content": "## What\n\nWork done after adoption, missing its impact declaration.\n",
        "parent_ids": ["20000000-0000-0000-0000-000000000003"],
        "created_at": "2026-08-03T00:00:00+00:00",
    })
    path = tmp_path / "record.json"
    path.write_text(json.dumps(graph))
    report = hg.run_check(path, EPOCH / "state.json", EPOCH_CONFIG)
    assert [f.node for f in report.violations()] == ["loud-comet-0004"]
    assert all(f.invariant == "I2" for f in report.violations())


def test_epoch_unresolvable_marker_is_violation():
    report = hg.run_check(EPOCH / "record.json", EPOCH / "state.json",
                          {"epoch": {"marker": "no-such-slug-0000"}})
    assert any(f.invariant == "I2" and "epoch.marker" in f.message
               for f in report.violations())


def test_staleness_reported_for_unreconciled_impacts():
    """Roll the HWM back one node; the impact of calm-heron-0003 becomes pending."""
    import json
    graph = json.loads((FIXTURES / "clean" / "state.json").read_text())
    for node in graph["nodes"]:
        node["content"] = node["content"].replace(
            "high_water_mark: dim-walrus-0004", "high_water_mark: brisk-otter-0002"
        )
    import tempfile, os
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(graph, f)
        path = Path(f.name)
    try:
        report = hg.run_check(FIXTURES / "clean" / "record.json", path)
        assert report.violations() == []
        infos = " | ".join(f.message + ":" + f.node for f in report.infos())
        assert "2 unreconciled" in infos
        assert "mellow-quartz-0102" in infos  # calm-heron's target has a pending impact
    finally:
        os.unlink(path)


# ---- the config defects that cost two arm-C runs their memory system ----------
#
# On the nine-run benchmark, `check --config .hypergraph/config.yml` was run
# before the config existed. It died with a raw FileNotFoundError traceback out
# of `read_text`, naming pathlib rather than the missing file. Two of three arm-C
# agents read that as "the contents are wrong", wrote a one-line stub
# (`backend: local`), and got "0 violations" — because the checker had silently
# fallen back to guessing the roots. Both runs then carried a config that
# declared neither `record_root` nor `state_root`.

def test_missing_config_fails_with_an_instruction_not_a_traceback(tmp_path):
    clean = FIXTURES / "clean"
    with pytest.raises(SystemExit) as excinfo:
        hg.main(["check", "--record", str(clean / "record.json"),
                 "--state", str(clean / "state.json"),
                 "--config", str(tmp_path / "config.yml")])
    message = str(excinfo.value)
    assert "no config at" in message
    assert "record_root" in message and "state_root" in message
    # The old failure was a stack ending in pathlib. If that name is back, the
    # agent is being shown the plumbing again instead of the problem.
    assert "Traceback" not in message and "pathlib" not in message


def test_unparseable_config_names_the_file(tmp_path):
    bad = tmp_path / "config.yml"
    bad.write_text("record_root: [unclosed\n")
    clean = FIXTURES / "clean"
    with pytest.raises(SystemExit) as excinfo:
        hg.main(["check", "--record", str(clean / "record.json"),
                 "--state", str(clean / "state.json"), "--config", str(bad)])
    assert str(bad) in str(excinfo.value)


def test_a_config_declaring_no_roots_warns_rather_than_passing_silently(tmp_path):
    """The stub config must not read as a clean bill of health."""
    stub = tmp_path / "config.yml"
    stub.write_text("backend: local\n")
    clean = FIXTURES / "clean"
    report = hg.run_check(clean / "record.json", clean / "state.json",
                          hg.load_config(stub), config_given=True)
    # Still a pass — the inferred root may be right, and a correct graph should
    # not fail over how its root was located.
    assert report.violations() == []
    warnings = [f.message for f in report.warnings()]
    assert any("declares no `record_root:`" in w for w in warnings), warnings
    assert any("declares no `state_root:`" in w for w in warnings), warnings


def test_inference_without_a_config_stays_silent():
    """No --config is a deliberate choice, not an oversight — do not nag."""
    clean = FIXTURES / "clean"
    report = hg.run_check(clean / "record.json", clean / "state.json")
    assert report.warnings() == []


def test_cli_reports_a_version():
    """preflight pins the installed version against pyproject; both need this."""
    import re
    with pytest.raises(SystemExit) as excinfo:
        hg.main(["--version"])
    assert excinfo.value.code == 0
    pyproject = (ROOT / "pyproject.toml").read_text()
    declared = re.search(r'^version = "([^"]+)"', pyproject, re.M).group(1)
    assert hg.__version__ == declared


def test_legacy_backend_key_warns_but_never_fails():
    """`backend:` is ignored since 0.0.4, and a missing key now means the node files.

    Warning, not violation: failing someone's CI over a key the tool no longer reads
    would be hostile, and the migration it names (re-homing) is not a five-second fix.
    """
    clean = FIXTURES / "clean"
    config = {"backend": "flywheel"}
    report = hg.run_check(clean / "record.json", clean / "state.json", config)
    warnings = [str(f) for f in report.warnings()]
    assert any("is ignored" in w and "mirror.md" in w for w in warnings), warnings
    assert report.violations() == []


def test_backend_local_and_a_missing_backend_key_are_both_silent():
    """A missing key is correct by construction now — there is one thing it can mean."""
    clean = FIXTURES / "clean"
    for config in ({"backend": "local"}, {}):
        report = hg.run_check(clean / "record.json", clean / "state.json", config)
        assert not [str(f) for f in report.warnings() if "backend" in str(f)]


# --------------------------------------------------- I1: what counts as a claim
#
# The unit-splitting rule was `bullets or paragraphs` — either, never both — so a
# `## Current` section containing any bullet had its prose paragraphs dropped from
# the check entirely. A checker that silently stops checking is worse than one that
# is noisy, and this one was silent for every state node that mixes the two, which is
# most of them. Found by a mode-A adoption of neural-whoop.

def test_a_paragraph_claim_is_checked_even_when_the_section_has_bullets():
    body = ("Status: working\n\n## Current\n\n"
            "This paragraph asserts something and cites nothing at all.\n\n"
            "- a bullet that does cite [rec: wise-anchor-1001]\n")
    units = hg.claim_units(body.split("## Current\n", 1)[1])
    uncited = [u for u in units if not hg.CITE_RE.search(u)]
    assert len(units) == 2
    assert uncited and uncited[0].startswith("This paragraph asserts")


def test_a_citation_on_a_wrapped_continuation_line_counts():
    """A unit is a bullet plus its continuation lines, not one line. The old rule
    reported correctly-cited prose as uncited, which taught adopters to reflow text
    to satisfy the checker."""
    body = ("- a claim long enough that its citation wrapped onto\n"
            "  the following line [rec: wise-anchor-1001]\n")
    units = hg.claim_units(body)
    assert len(units) == 1
    assert hg.CITE_RE.search(units[0])


def test_nested_sub_bullets_are_their_own_claims():
    """Each needs its own citation — a parent's does not cover them."""
    body = ("- parent [rec: wise-anchor-1001]\n"
            "  - child with no citation\n")
    units = hg.claim_units(body)
    assert len(units) == 2
    assert not hg.CITE_RE.search(units[1])


def test_headings_and_code_blocks_are_not_claims():
    """Checking paragraphs surfaced four warnings on this repo's own state graph, all
    of them markdown headings. A heading is structure and a code block asserts
    nothing; demanding citations on either teaches people to cite noise."""
    body = ("### A heading needs no citation\n\n"
            "Prose under it does [rec: wise-anchor-1001].\n\n"
            "```\nrun --this --command\n```\n")
    units = hg.claim_units(body)
    assert len(units) == 1
    assert units[0].startswith("Prose under it")


def test_a_colon_lead_in_to_a_bullet_list_is_not_a_claim():
    """"Two failures are measured rather than suspected:" is punctuation for the list
    that follows, and the bullets carry the evidence. Three adopted state nodes hit
    this the moment paragraphs started being checked."""
    body = ("Two failures are measured rather than suspected:\n\n"
            "- the first [rec: wise-anchor-1001]\n"
            "- the second [rec: wise-anchor-1001]\n")
    assert len(hg.claim_units(body)) == 2


def test_a_paragraph_that_merely_ends_in_a_colon_is_still_a_claim():
    """The exemption is for lead-ins, not for any sentence with a colon in it."""
    body = "The rule is explicit: nothing here cites anything.\n\nAnd nor does this.\n"
    assert len(hg.claim_units(body)) == 2


# ---- parsing trust: fences, duplicates, tight slugs, comments (0.1.0 gate) ----

import json as _json


def _mutated(tmp_path, fixture, name, mutate):
    """Copy a clean fixture graph JSON with one node's content rewritten."""
    graph = _json.loads((FIXTURES / "clean" / fixture).read_text())
    for node in graph["nodes"]:
        if node["slug_name"] == name:
            node["content"] = mutate(node["content"])
    path = tmp_path / fixture
    path.write_text(_json.dumps(graph))
    return path


def test_live_dogfood_graph_stays_green(tmp_path):
    """This repo's own committed graph must stay green under every checker change.

    93+ record and 25+ state nodes of real usage: the standing backward-compat net
    for parsing changes — a stricter rule that flags the live graph is a defect in
    the rule, not the graph."""
    config = hg.load_config(ROOT / ".hypergraph" / "config.yml")
    graph_dir = ROOT / (config.get("graph_dir") or ".hypergraph/graph")
    for kind in ("record", "state"):
        payload = hg.export_graph_json(graph_dir, kind)
        (tmp_path / f"{kind}.json").write_text(_json.dumps(payload))
    report = hg.run_check(tmp_path / "record.json", tmp_path / "state.json",
                          config, repo_root=ROOT)
    assert report.violations() == [], [str(f) for f in report.violations()]


def test_split_sections_ignores_headings_inside_fences():
    pre, sections = hg.split_sections(
        "intro\n\n```md\n## State Impact\nnone: just an example\n```\n\n## Real\nbody\n")
    assert "state impact" not in sections
    assert sections["real"] == "body"
    assert "## State Impact" in pre  # fenced example stays in the enclosing text


def test_split_sections_first_body_wins_on_duplicate_heading():
    _pre, sections = hg.split_sections("## Current\nfirst\n\n## Current\nsecond\n")
    assert sections["current"] == "first"


def test_fenced_state_impact_does_not_satisfy_i2(tmp_path):
    record = _mutated(tmp_path, "record.json", "calm-heron-0003", lambda c:
                      "## What\n\nwork\n\n```\n## State Impact\nnone: fenced example\n```\n")
    report = hg.run_check(record, FIXTURES / "clean" / "state.json")
    assert any(f.invariant == "I2" and "missing" in f.message and
               f.node == "calm-heron-0003" for f in report.violations())


def test_duplicate_load_bearing_heading_is_a_violation(tmp_path):
    state = _mutated(tmp_path, "state.json", "quiet-lantern-0103", lambda c:
                     c + "\n## Provenance\n\n- dim-walrus-0004 — a second section\n")
    report = hg.run_check(FIXTURES / "clean" / "record.json", state)
    assert any(f.invariant == "I4" and "duplicate" in f.message and
               f.node == "quiet-lantern-0103" for f in report.violations())


def test_duplicate_state_impact_heading_is_a_violation(tmp_path):
    record = _mutated(tmp_path, "record.json", "calm-heron-0003", lambda c:
                      c + "\n## State Impact\nnone: a second declaration\n")
    report = hg.run_check(record, FIXTURES / "clean" / "state.json")
    assert any(f.invariant == "I2" and "duplicate" in f.message and
               f.node == "calm-heron-0003" for f in report.violations())


def test_url_tail_in_provenance_is_not_read_as_a_slug(tmp_path):
    """`- <slug> — see https://ci.example/fast-lane-1234` must not flag the URL."""
    state = _mutated(tmp_path, "state.json", "quiet-lantern-0103", lambda c:
                     c.rstrip() + " — see https://ci.example/build/fast-lane-1234\n")
    report = hg.run_check(FIXTURES / "clean" / "record.json", state)
    assert report.violations() == [], [str(f) for f in report.violations()]


def test_provenance_accepts_rec_citation_as_fallback(tmp_path):
    state = _mutated(tmp_path, "state.json", "quiet-lantern-0103", lambda c:
                     c.rstrip() + "\n- see the schema decision [rec: brisk-otter-0002]\n")
    report = hg.run_check(FIXTURES / "clean" / "record.json", state)
    assert report.violations() == [], [str(f) for f in report.violations()]


def test_provenance_bullet_without_any_slug_still_fails(tmp_path):
    state = _mutated(tmp_path, "state.json", "quiet-lantern-0103", lambda c:
                     c.rstrip() + "\n- a bullet with no citation at all\n")
    report = hg.run_check(FIXTURES / "clean" / "record.json", state)
    assert any(f.invariant == "I4" and "no record slug" in f.message
               for f in report.violations())


def test_url_tail_in_evidence_field_is_not_read_as_a_slug(tmp_path):
    state = _mutated(tmp_path, "state.json", "mellow-quartz-0102", lambda c: c.replace(
        "evidence: brisk-otter-0002]",
        "evidence: brisk-otter-0002, https://ci.example/run/fast-lane-1234]"))
    report = hg.run_check(FIXTURES / "clean" / "record.json", state)
    assert report.violations() == [], [str(f) for f in report.violations()]


def test_comment_above_status_line_passes_i6(tmp_path):
    state = _mutated(tmp_path, "state.json", "quiet-lantern-0103", lambda c:
                     "<!-- reviewed 2026-08-18 -->\n" + c)
    report = hg.run_check(FIXTURES / "clean" / "record.json", state)
    assert report.violations() == [], [str(f) for f in report.violations()]


# ---- guarded export loading + timestamp ordering (0.1.0 gate, U2) -------------


def test_check_on_missing_export_exits_2_with_instruction(tmp_path, capsys):
    rc = hg.main(["check", "--record", str(tmp_path / "record.json"),
                  "--state", str(FIXTURES / "clean" / "state.json")])
    assert rc == 2
    err = capsys.readouterr().err
    assert "no export at" in err
    assert "hypergraph export" in err


def test_check_on_truncated_export_exits_2_with_instruction(tmp_path, capsys):
    bad = tmp_path / "record.json"
    bad.write_text((FIXTURES / "clean" / "record.json").read_text()[:180])
    rc = hg.main(["check", "--record", str(bad),
                  "--state", str(FIXTURES / "clean" / "state.json")])
    assert rc == 2
    err = capsys.readouterr().err
    assert "not valid JSON" in err
    assert "hypergraph export" in err


def test_created_key_is_chronological_and_total():
    z, offset = "2026-08-02T02:00:00Z", "2026-08-02T10:00:00+09:00"  # 02:00 vs 01:00 UTC
    assert hg.created_key(offset) < hg.created_key(z)   # instants, not strings
    assert sorted([offset, z]) == [z, offset]           # raw strings disagree
    assert hg.created_key("") < hg.created_key(z)       # unparseable sorts first
    assert hg.created_key("garbage", "a") < hg.created_key("garbage", "b")


def _tsnode(slug, created_at, parents=()):
    return hg.Node(node_id="id-" + slug, slug=slug, title=slug, content="",
                   parent_ids=list(parents), created_at=created_at)


def test_unreconciled_enumeration_orders_by_instant_not_string():
    root = _tsnode("wise-root-0001", "2026-08-01T00:00:00+00:00")
    early = _tsnode("early-node-0002", "2026-08-02T10:00:00+09:00",  # 01:00 UTC
                    ["id-wise-root-0001"])
    late = _tsnode("late-node-0003", "2026-08-02T02:00:00+00:00",    # 02:00 UTC
                   ["id-wise-root-0001"])
    nodes = {n.node_id: n for n in (root, early, late)}
    record = hg.Graph(nodes=nodes, by_slug={n.slug: n for n in nodes.values()})
    out = hg.unreconciled_nodes(record, ["wise-root-0001"], root)
    assert [n.slug for n in out] == ["early-node-0002", "late-node-0003"]
    # the raw strings sort the other way round — this is what the fix is for
    assert sorted([early.created_at, late.created_at]) == [late.created_at,
                                                           early.created_at]
