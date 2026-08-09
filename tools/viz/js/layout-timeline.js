// ---------------------------------------------------------------- timeline
// The record graph is a timeline with a few concurrent threads, not a DAG to be
// ranked: on this repo it is 29 layers deep and 3 wide, which a layered layout
// renders as a 1:15 ribbon. Here time runs along x and `git log` lanes stack
// along y, so the same 39 nodes read as a wide strip at full size.
//
// Lanes come from the payload (hypergraph.py: lane_layout), so they are computed
// once, deterministically, from the real parent relation.

const MIN_STEP = Math.round(RANK_STEP * 0.35);   // "time" mode: idle gaps compress
const MAX_STEP = RANK_STEP * 3;                  // …and busy days still separate

function recordChrono() {
  return DATA.record.nodes.slice().sort((a, b) => a.chrono - b.chrono);
}

// x per record node. "rank" gives every node the same slice of width; "time"
// spaces them by real elapsed time with both ends clamped, so a three-week idle
// gap does not push the next month off screen and a busy hour is still legible.
function timelineX(nodes) {
  const x = {};
  if (show.xaxis === "rank") {
    nodes.forEach(n => x[n.slug] = n.chrono * RANK_STEP);
    return x;
  }
  const ms = nodes.map(n => Date.parse(n.created_at || "") || 0);
  const gaps = [];
  for (let i = 1; i < ms.length; i++) gaps.push(Math.max(0, ms[i] - ms[i - 1]));
  const sorted = gaps.slice().sort((a, b) => a - b);
  const median = sorted.length ? sorted[sorted.length >> 1] : 0;
  const perMs = RANK_STEP / Math.max(1, median);   // median gap ≈ one rank step
  let at = 0;
  nodes.forEach((n, i) => {
    if (i) at += Math.min(MAX_STEP, Math.max(MIN_STEP, (ms[i] - ms[i - 1]) * perMs));
    x[n.slug] = Math.round(at);
  });
  return x;
}

function layoutTimeline(pos) {
  const nodes = recordChrono();
  const x = timelineX(nodes);
  nodes.forEach(n => pos[n.slug] = { x: x[n.slug], y: n.lane * LANE_H });
  if (stVis()) {  // state visible alongside: a plain column past the strip
    const right = Math.max(0, ...nodes.map(n => x[n.slug])) + CW / 2 + 120 + NW / 2;
    DATA.state.nodes.forEach(n => pos[n.slug] = { x: right, y: n.seq * (NH + 22) });
  }
  return pos;
}

// Furniture drawn behind the chips: lane rules, a date gutter, and the
// high-water mark. Everything is derived from `pos`, so dragging a chip does not
// invalidate it.
function timelineFurniture(pos) {
  const nodes = recordChrono().filter(n => pos[n.slug]);
  if (!nodes.length) return null;
  const xs = nodes.map(n => pos[n.slug].x);
  const x0 = Math.min(...xs) - CW / 2 - 24, x1 = Math.max(...xs) + CW / 2 + 24;
  const laneCount = Math.max(...nodes.map(n => n.lane)) + 1;

  const ticks = [];           // one label per new calendar day, at its first node
  let lastDay = null;
  nodes.forEach(n => {
    const day = (n.created_at || "").slice(0, 10);
    if (!day || day === lastDay) return;
    lastDay = day;
    ticks.push({ x: pos[n.slug].x, day, label: day.slice(5) });
  });

  const hwm = DATA.reconciliation.high_water_mark;
  const hwmX = hwm && pos[hwm] ? pos[hwm].x + CW / 2 + 8 : null;
  return { x0, x1, laneCount, ticks, hwmX,
           top: -LANE_H, bottom: (laneCount - 1) * LANE_H + LANE_H };
}
