"""Live mode: the page polls a sibling JSON file and pulses what is new.

Served over a real local http server, because that is the only way live mode
works — browsers refuse cross-file fetch from `file://`, and the page says so
rather than failing silently.
"""
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from conftest import FIXTURE, VIEWPORT, hg

POLL_MS = 1000


@pytest.fixture
def live_site(tmp_path):
    """A directory holding viz.html + viz.data.json, served over http."""
    out = tmp_path / "viz.html"
    assert hg.main(["viz", "--live", "--live-interval", "1",
                    "--record", str(FIXTURE / "record.json"),
                    "--state", str(FIXTURE / "state.json"),
                    "-o", str(out)]) == 0
    data_path = tmp_path / "viz.data.json"
    assert data_path.exists()
    # the page must be rebuilt from the current sources, not the bundled constant
    out.write_text(hg.render_viz(FIXTURE / "record.json", FIXTURE / "state.json",
                                 template=hg.assemble_viz_template(),
                                 live={"url": "viz.data.json", "interval_ms": POLL_MS}))

    handler = partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/viz.html", data_path
    server.shutdown()
    server.server_close()


def test_live_page_polls_and_pulses_new_nodes(browser, live_site):
    url, data_path = live_site
    ctx = browser.new_context(viewport=VIEWPORT, color_scheme="light")
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url)
    page.wait_for_selector("#world")
    page.click('#presets button[data-preset="timeline"]')
    page.wait_for_function("() => document.querySelectorAll('#nodes g.node').length > 0")

    assert page.is_visible("#live"), "the live indicator must appear"
    before = page.evaluate("() => document.querySelectorAll('#nodes g.node').length")

    # Append a node to the served data, exactly as a fresh `viz --live` would.
    data = json.loads(data_path.read_text())
    tip = max(data["record"]["nodes"], key=lambda n: n["chrono"])
    data["record"]["nodes"].append({
        **tip, "slug": "fresh-node-9999", "title": "Something just happened",
        "parents": [tip["slug"]], "chrono": tip["chrono"] + 1, "seq": tip["seq"] + 1,
        "is_root": False, "is_hwm": False, "unreconciled": True,
        "created_at": "2026-08-10T00:00:00+00:00",
    })
    data_path.write_text(json.dumps(data))

    page.wait_for_function(
        "n => document.querySelectorAll('#nodes g.node').length > n",
        arg=before, timeout=10_000)
    assert page.is_visible('#nodes g.node[data-slug="fresh-node-9999"]')
    assert "new" in page.text_content("#live")
    # the pulse ring is a transient child of the new node
    assert page.evaluate(
        """() => document.querySelector('#nodes g.node[data-slug="fresh-node-9999"]')
                 .querySelectorAll("rect animate").length""") == 1
    assert errors == []
    ctx.close()


def test_live_mode_is_off_by_default_and_fetches_nothing():
    """The default output must stay self-contained: no DATA.live, no polling."""
    html = hg.render_viz(FIXTURE / "record.json", FIXTURE / "state.json",
                         template=hg.assemble_viz_template())
    assert '"live"' not in html.split("const DATA = ")[1].split(";\n")[0]
    assert "http://" not in html.replace("http://www.w3.org/", "")


def test_live_requires_an_output_path(tmp_path, capsys):
    rc = hg.main(["viz", "--live", "--record", str(FIXTURE / "record.json"),
                  "--state", str(FIXTURE / "state.json")])
    assert rc == 2
    assert "needs -o" in capsys.readouterr().err
