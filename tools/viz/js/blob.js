// ------------------------------------------------------- blob hull geometry
// Andrew's monotone chain; deterministic sort. Colinear inputs collapse to
// the two extreme points (capsule fallback in blobPath).
function convexHull(pts) {
  const p = pts.slice().sort((a, b) => a.x - b.x || a.y - b.y);
  if (p.length < 3) return p;
  const cross = (o, a, b) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
  const half = seq => {
    const out = [];
    for (const pt of seq) {
      while (out.length >= 2 && cross(out[out.length - 2], out[out.length - 1], pt) <= 0)
        out.pop();
      out.push(pt);
    }
    out.pop();
    return out;
  };
  return half(p).concat(half(p.slice().reverse()));
}

function blobPath(members, pos) {
  const cards = show.style === "cards";
  const RB = cards ? BPAD : R + BPAD;
  let pts = members.map(s => pos[s]).filter(Boolean);
  if (!pts.length) return null;
  if (cards) pts = pts.flatMap(p => [  // hull must wrap the full card rects
    { x: p.x - NW / 2, y: p.y - NH / 2 }, { x: p.x + NW / 2, y: p.y - NH / 2 },
    { x: p.x - NW / 2, y: p.y + NH / 2 }, { x: p.x + NW / 2, y: p.y + NH / 2 }]);
  if (pts.length === 1) {
    const p = pts[0];
    return `M ${p.x - RB} ${p.y} a ${RB} ${RB} 0 1 0 ${2 * RB} 0` +
           ` a ${RB} ${RB} 0 1 0 ${-2 * RB} 0 Z`;
  }
  const hull = convexHull(pts);
  if (hull.length < 3) {  // 2 members, or all colinear: capsule
    const a = hull[0], b = hull[hull.length - 1];
    const dx = b.x - a.x, dy = b.y - a.y;
    const d = Math.sqrt(dx * dx + dy * dy) || 1;
    const nx = -dy / d * RB, ny = dx / d * RB;
    return `M ${a.x + nx} ${a.y + ny}` +
           ` A ${RB} ${RB} 0 0 1 ${a.x - nx} ${a.y - ny}` +
           ` L ${b.x - nx} ${b.y - ny}` +
           ` A ${RB} ${RB} 0 0 1 ${b.x + nx} ${b.y + ny} Z`;
  }
  let cx = 0, cy = 0;
  hull.forEach(p => { cx += p.x; cy += p.y; });
  cx /= hull.length; cy /= hull.length;
  const ex = hull.map(p => {  // pad: push vertices out radially from centroid
    const dx = p.x - cx, dy = p.y - cy;
    const d = Math.sqrt(dx * dx + dy * dy) || 1;
    return { x: p.x + dx / d * RB, y: p.y + dy / d * RB };
  });
  const n = ex.length;  // closed Catmull-Rom -> cubic Bezier
  let d = `M ${ex[0].x} ${ex[0].y}`;
  for (let i = 0; i < n; i++) {
    const p0 = ex[(i + n - 1) % n], p1 = ex[i], p2 = ex[(i + 1) % n], p3 = ex[(i + 2) % n];
    d += ` C ${p1.x + (p2.x - p0.x) / 6} ${p1.y + (p2.y - p0.y) / 6},` +
         ` ${p2.x - (p3.x - p1.x) / 6} ${p2.y - (p3.y - p1.y) / 6}, ${p2.x} ${p2.y}`;
  }
  return d + " Z";
}

function blobLabelPos(members, pos) {
  const pts = members.map(s => pos[s]).filter(Boolean);
  const off = (show.style === "cards" ? NH / 2 + BPAD : R + BPAD) + 8;
  let cx = 0, top = 1e9;
  pts.forEach(p => { cx += p.x; top = Math.min(top, p.y); });
  return { x: cx / pts.length, y: top - off };
}

// All blob label positions at once, with a deterministic de-overlap pass:
// a label colliding with an already-placed one is pushed up until clear.
function blobLabelPositions(pos) {
  const placed = [], out = {};
  hyperedges().list.forEach(h => {
    const lp = blobLabelPos(h.members, pos);
    const w = h.state.length * 6.3;
    let y = lp.y, moved = true;
    while (moved) {
      moved = false;
      for (const p of placed) {
        if (Math.abs(lp.x - p.x) < (w + p.w) / 2 + 8 && Math.abs(y - p.y) < 13) {
          y = p.y - 14;  // strictly decreases, so this terminates
          moved = true;
        }
      }
    }
    placed.push({ x: lp.x, y, w });
    out[h.state] = { x: lp.x, y };
  });
  return out;
}

