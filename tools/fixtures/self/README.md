# `self` fixture — a frozen snapshot of this repo's own graph

39 record nodes, 12 state nodes, 176 cross-graph links, captured at
`gilded-pebble-5687` (2026-08-09). This is the graph the viz overhaul was measured
against, and it is frozen here so the browser baselines in `tests/browser/` stay
stable while the live graph keeps growing.

Regenerate deliberately, never automatically — a refresh re-blesses every baseline:

    uv run tools/hypergraph.py export --config .hypergraph/config.yml
    cp .hypergraph/cache/{record,state}.json tools/fixtures/self/
    HG_VIZ_UPDATE_BASELINE=1 uv run pytest tests/browser/
