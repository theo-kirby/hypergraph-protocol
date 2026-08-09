"""Tag chips in a real browser: they filter, and they never restyle a node.

The second half matters as much as the first. A tag is annotation with no standing
in the protocol, so letting one change how a node is *drawn* would give it standing
in the picture that it does not have anywhere else.
"""
import json

import pytest

from conftest import FIXTURE, VIEWPORT, hg, open_view

TAGGED = {"kind:experiment": 0, "outcome:GREEN": 1}   # name → which nodes get it


@pytest.fixture(scope="session")
def tagged_html(tmp_path_factory):
    """The self fixture with tags painted onto alternating record nodes."""
    out = tmp_path_factory.mktemp("viztags")
    record = json.loads((FIXTURE / "record.json").read_text())
    for i, node in enumerate(record["nodes"]):
        node["tags"] = [name for name, parity in TAGGED.items() if i % 2 == parity]
    (out / "record.json").write_text(json.dumps(record))
    (out / "state.json").write_text((FIXTURE / "state.json").read_text())
    page = out / "viz.html"
    page.write_text(hg.render_viz(out / "record.json", out / "state.json",
                                  template=hg.assemble_viz_template()))
    return page


@pytest.fixture
def tagged_page(browser, tagged_html):
    ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=1,
                              color_scheme="light", reduced_motion="reduce")
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.goto(f"file://{tagged_html}")
    pg.wait_for_selector("#world")
    pg.errors = errors
    yield pg
    ctx.close()


def test_a_graph_with_no_tags_shows_no_chip_row(page):
    """The control does not exist until a project opts in."""
    open_view(page, "timeline")
    assert page.eval_on_selector("#tagchips", "el => el.hidden") is True
    assert page.errors == []


def test_chips_render_with_their_declared_counts(tagged_page):
    open_view(tagged_page, "timeline")
    assert tagged_page.eval_on_selector("#tagchips", "el => el.hidden") is False
    chips = tagged_page.eval_on_selector_all(
        "#tagchips button", "els => els.map(e => e.dataset.tag)")
    assert sorted(chips) == ["kind:experiment", "outcome:GREEN"]
    counts = tagged_page.eval_on_selector_all(
        "#tagchips button i", "els => els.map(e => +e.textContent)")
    assert all(c > 0 for c in counts)
    assert tagged_page.errors == []


def test_clicking_a_chip_dims_everything_without_it(tagged_page):
    open_view(tagged_page, "timeline")
    lit = "() => [...document.querySelectorAll('#nodes g.node')]" \
          ".filter(g => +g.getAttribute('opacity') === 1).length"
    before = tagged_page.evaluate(lit)
    tagged_page.click('#tagchips button[data-tag="kind:experiment"]')
    tagged_page.wait_for_timeout(80)
    narrowed = tagged_page.evaluate(lit)
    assert 0 < narrowed < before

    # a second chip widens the selection — chips are OR within, not AND
    tagged_page.click('#tagchips button[data-tag="outcome:GREEN"]')
    tagged_page.wait_for_timeout(80)
    assert tagged_page.evaluate(lit) > narrowed

    # and turning both off restores the whole graph
    tagged_page.click('#tagchips button[data-tag="kind:experiment"]')
    tagged_page.click('#tagchips button[data-tag="outcome:GREEN"]')
    tagged_page.wait_for_timeout(80)
    assert tagged_page.evaluate(lit) == before
    assert tagged_page.errors == []


def test_tags_change_no_node_geometry_or_colour(browser, tagged_html, viz_html):
    """Same graph, tags added: the drawing must be identical."""
    shapes = ("() => [...document.querySelectorAll('#nodes g.node')].map(g => {"
              "const s = g.firstChild;"
              "return [g.dataset.slug, s.tagName, s.getAttribute('fill'),"
              " s.getAttribute('stroke'), g.getAttribute('transform')].join('|');})")
    out = []
    for html in (viz_html, tagged_html):
        ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=1,
                                  color_scheme="light", reduced_motion="reduce")
        pg = ctx.new_page()
        pg.goto(f"file://{html}")
        pg.wait_for_selector("#world")
        open_view(pg, "timeline")
        out.append(pg.evaluate(shapes))
        ctx.close()
    assert len(out[0]) > 10, "nothing was measured — the selector stopped matching"
    assert out[0] == out[1]
