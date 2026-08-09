// -------------------------------------------------------------------- live
// `viz --live` writes a sibling JSON file and sets DATA.live. The page then
// re-reads that file on an interval and pulses whatever is new.
//
// This is the one feature that breaks the page's self-contained property, which
// is why it exists only when the flag asked for it: without DATA.live not a byte
// of network code runs, and the default output still fetches nothing.
//
// Browsers refuse cross-file fetch from file://, so a live page has to be served
// over http. Rather than fail silently, the indicator says so and polling stops.

const LIVE_MAX_FAILS = 3;
const PULSE_MS = 1800;

function liveSignature(data) {
  // Cheap and sufficient: what exists, and when the graphs were exported.
  return [data.record.nodes.length, data.state.nodes.length, data.links.length,
          data.record.exported_at, data.state.exported_at,
          (data.reconciliation.high_water_frontier || []).join(",")].join("|");
}

function liveStatus(text, tone) {
  const box = document.getElementById("live");
  if (!box) return;
  box.hidden = false;
  box.dataset.tone = tone;
  box.querySelector("span").textContent = text;
}

// A ring drawn around the node and faded out with SMIL — no CSS, so it works the
// same way in the exported SVG, and no timers that could outlive a re-render.
function pulseNode(slug) {
  const g = nodeEls[slug];
  if (!g) return;
  const d = dimsOf(slug), pad = 7;
  const circle = styleFor(bySlug[slug]) === "circle";
  const ring = el("rect", {
    x: (circle ? -d.w / 2 : 0) - pad, y: (circle ? -d.h / 2 : 0) - pad,
    width: d.w + pad * 2, height: d.h + pad * 2, rx: 12,
    fill: "none", stroke: T().status.open, "stroke-width": 3,
    "pointer-events": "none",
  });
  ring.appendChild(el("animate", { attributeName: "opacity", from: 0.95, to: 0,
    dur: (PULSE_MS / 1000) + "s", fill: "freeze" }));
  g.appendChild(ring);
  setTimeout(() => ring.remove(), PULSE_MS + 200);
}

// Swap in a fresh payload. Everything derived from DATA has to be dropped, and
// the list is the point: a cache that survives a data swap is a stale drawing
// that looks live.
// DATA.settings is deliberately *not* swapped: it carries the config's blob
// tuning, which belongs to the page rather than to the graph. A refresh that
// reset it would pull a slider out from under you mid-adjustment.
function adoptData(fresh) {
  const before = new Set(Object.keys(bySlug));
  DATA.record = fresh.record;
  DATA.state = fresh.state;
  DATA.links = fresh.links;
  DATA.reconciliation = fresh.reconciliation;
  for (const slug in bySlug) delete bySlug[slug];
  DATA.record.nodes.forEach(n => bySlug[n.slug] = { graph: "record", node: n });
  DATA.state.nodes.forEach(n => bySlug[n.slug] = { graph: "state", node: n });
  _hyper = null;
  _spineRank = null;
  registerPucks();
  // A claim that no longer exists cannot stay collapsed.
  [...collapsed].forEach(st => { if (!bySlug[st]) collapsed.delete(st); });
  blobCache.clear();
  for (const k in positions) delete positions[k];   // layouts depend on the data
  if (selected && !bySlug[selected]) selected = null;
  hovered = null;
  renderAll();
  renderPanel();
  const added = Object.keys(bySlug).filter(s => !before.has(s));
  added.forEach(pulseNode);
  return added.length;
}

function startLive() {
  if (!DATA.live) return;
  let signature = liveSignature(DATA), fails = 0, timer = null;
  liveStatus("live", "ok");

  const poll = () => {
    // Cache-bust with the signature we already have: no clock is read, so the
    // page stays deterministic under test.
    fetch(DATA.live.url + "?v=" + encodeURIComponent(signature), { cache: "no-store" })
      .then(r => r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)))
      .then(fresh => {
        fails = 0;
        const next = liveSignature(fresh);
        if (next === signature) { liveStatus("live", "ok"); return; }
        signature = next;
        const added = adoptData(fresh);
        liveStatus(added ? "+" + added + " new" : "updated", "new");
      })
      .catch(err => {
        if (++fails < LIVE_MAX_FAILS) { liveStatus("live · retrying", "warn"); return; }
        clearInterval(timer);
        liveStatus("live off — serve over http", "warn");
        console.warn("[hypergraph] live polling stopped:", err.message);
      });
  };
  timer = setInterval(poll, Math.max(1000, DATA.live.interval_ms || 5000));
}
