#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# ///
"""Dev tool: bundle `tools/viz/*` into the `VIZ_TEMPLATE` constant of hypergraph.py.

`tools/hypergraph.py` must stay one file you can copy anywhere and run, and the page
it emits must stay self-contained. Those two properties are why the viz sources live
split under `tools/viz/` and are *concatenated at build time* rather than fetched at
run time. This script is the build step; it ships with the repo, not with the wheel.

    tools/bundle_viz.py            # rewrite the constant in place
    tools/bundle_viz.py --check    # exit 1 if the constant is stale (CI / pytest)

`hypergraph.py viz --dev` reads `tools/viz/` directly, so the edit loop needs no
rebundle — but the default path always uses the constant, and
`tests/test_viz.py::test_viz_bundle_in_sync` fails if you edit JS and forget to run
this.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tools" / "hypergraph.py"
VIZ_DIR = ROOT / "tools" / "viz"
BEGIN = "# --- BEGIN GENERATED VIZ TEMPLATE ---\n"
END = "# --- END ---\n"


def _hypergraph():
    """Import tools/hypergraph.py by path — the assembly lives there so that
    `viz --dev` and this bundler can never disagree about how parts concatenate."""
    spec = importlib.util.spec_from_file_location("hypergraph_bundle_src", TARGET)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hypergraph_bundle_src"] = mod
    spec.loader.exec_module(mod)
    return mod


def build_template(viz_dir: Path = VIZ_DIR) -> str:
    return _hypergraph().assemble_viz_template(viz_dir)


def render_block(template: str) -> str:
    """The generated region, marker lines excluded."""
    # The constant is an r-string, so the payload may contain neither a triple quote
    # nor a trailing backslash (which would escape the closing quote).
    if '"""' in template:
        raise SystemExit("refusing to bundle: the page contains a triple quote")
    if template.rstrip("\n").endswith("\\"):
        raise SystemExit("refusing to bundle: the page ends in a backslash")
    return ("# Generated from tools/viz/ by tools/bundle_viz.py — do not edit in place.\n"
            "# Edit the sources and re-run the bundler.\n"
            'VIZ_TEMPLATE = r"""' + template + '"""\n')


def splice(source: str, block: str) -> str:
    i = source.index(BEGIN) + len(BEGIN)
    j = source.index(END, i)
    return source[:i] + block + source[j:]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bundle_viz.py", description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if hypergraph.py is out of date instead of rewriting it")
    args = ap.parse_args(argv)

    source = TARGET.read_text()
    updated = splice(source, render_block(build_template()))
    if args.check:
        if updated == source:
            print("viz bundle is up to date")
            return 0
        print("viz bundle is STALE — run tools/bundle_viz.py", file=sys.stderr)
        return 1
    if updated == source:
        print("viz bundle already up to date")
        return 0
    TARGET.write_text(updated)
    print(f"bundled tools/viz/ into {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
