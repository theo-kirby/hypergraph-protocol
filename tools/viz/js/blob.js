// ------------------------------------------------------------------- blobs
// Organic outlines around a set of nodes: the geometry behind a hyperedge.
//
// The signed-distance-field half of this file is ported from the excaligraph
// project (src/geometry/blob.ts, MIT licence) and condensed for the browser.
// The algorithm, its parameter names and its commentary are that project's; the
// bugs in the transcription are ours. No URL here on purpose — this page must
// stay self-contained, and a test asserts it fetches nothing.
//
// A hyperedge joins many nodes at once, so an arrow will not do — we fill a blob
// that contains every member. A convex hull will not do either: the hull of
// three far-apart nodes swallows everything between them, member or not. So:
//
//   1. every member contributes its own signed distance, pushed out by `padding`;
//   2. a band of half-width `corridor` runs along a minimum spanning tree of the
//      member centres, so far-apart members stay one connected blob;
//   3. the pieces join with a *smooth* minimum, so two close members bulge into
//      one body instead of showing a seam;
//   4. every non-member is subtracted, so the boundary bends around a node that
//      happens to sit in the way.
//
// Then the zero contour comes out by marching squares, gets simplified, and is
// drawn as a closed curve. It is plain arithmetic on a fixed grid: same input,
// same points, every time — which is the rule this page is held to anyway.

// Tuned for this page's scale (nodes are 32px circles or ~160-240px cards).
// Every field here is live: the Blob tuning sliders (tuning.js) write straight
// into this object, and each reach below is read at call time, so a slider moves
// the geometry with no re-plumbing. `fillOpacity` is a percentage.
const BLOB = { padding: 15, corridor: 10, smoothing: 18, clearance: 11,
               resolution: 5, tolerance: 1.4, maxPoints: 220, dragCoarsen: 2.5,
               fillOpacity: 14, strokeWidth: 1.2, labelSize: 10.5 };
const BLOB_MAX_SAMPLES = 60000;   // per blob; coarsen rather than stall
// Total grid samples one render may spend across *all* blobs. 12 blobs still get
// the full 60k each; 59 blobs get 12k each and coarsen instead of taking seven
// seconds. Sampling was 98% of the first paint at 500 nodes.
const BLOB_SAMPLE_BUDGET = 720000;
// A tile of the sampling grid. Everything further than its own influence radius
// from a tile cannot change the field inside it, so each tile samples a pruned
// set — see traceContour.
const BLOB_TILE = 24;
// Below this zoom the field's detail is invisible anyway, so the cheap hull is
// the honest choice. A drag no longer falls back to it — see blobFieldMode.
const BLOB_FIELD_MIN_ZOOM = 0.3;

// ------------------------------------------------------- fast fallback: hull
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

// A member contributes its whole box to the hull, so the outline wraps chips,
// cards and circles alike — the shape depends on the layout, not on one toggle.
function memberOutline(slug, pos) {
  const p = pos[slug];
  if (!p) return [];
  if (styleFor(bySlug[slug]) === "circle") return [p];
  const d = dimsOf(slug);
  return [{ x: p.x - d.w / 2, y: p.y - d.h / 2 }, { x: p.x + d.w / 2, y: p.y - d.h / 2 },
          { x: p.x - d.w / 2, y: p.y + d.h / 2 }, { x: p.x + d.w / 2, y: p.y + d.h / 2 }];
}

function blobPath(members, pos) {
  const circles = show.style === "circles";
  const RB = circles ? R + BPAD : BPAD;
  const pts = members.flatMap(s => memberOutline(s, pos));
  if (!pts.length) return null;
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
  return closedCurve(ex.map(p => [p.x, p.y]));
}

// Closed Catmull-Rom through the loop, as cubic Beziers.
function closedCurve(loop) {
  const n = loop.length;
  if (n < 3) return null;
  let d = `M ${loop[0][0]} ${loop[0][1]}`;
  for (let i = 0; i < n; i++) {
    const p0 = loop[(i + n - 1) % n], p1 = loop[i];
    const p2 = loop[(i + 1) % n], p3 = loop[(i + 2) % n];
    d += ` C ${p1[0] + (p2[0] - p0[0]) / 6} ${p1[1] + (p2[1] - p0[1]) / 6},` +
         ` ${p2[0] - (p3[0] - p1[0]) / 6} ${p2[1] - (p3[1] - p1[1]) / 6},` +
         ` ${p2[0]} ${p2[1]}`;
  }
  return d + " Z";
}

// ------------------------------------------------- signed distance functions
// Each returns 0 on the outline, negative inside and positive outside, in px.
// Subtracting a constant grows the shape by that much and rounds its corners,
// which is exactly what `padding` should do.
function sdRectangle(px, py, b) {
  const dx = Math.abs(px - (b.x + b.width / 2)) - b.width / 2;
  const dy = Math.abs(py - (b.y + b.height / 2)) - b.height / 2;
  return Math.hypot(Math.max(dx, 0), Math.max(dy, 0)) + Math.min(Math.max(dx, dy), 0);
}

// Exact for a circle. For a stretched ellipse it reads a little short along the
// long axis, which errs toward a tighter blob, never a looser one.
function sdEllipse(px, py, b) {
  const hw = Math.max(b.width / 2, 1e-6), hh = Math.max(b.height / 2, 1e-6);
  const norm = Math.hypot((px - (b.x + hw)) / hw, (py - (b.y + hh)) / hh);
  return (norm - 1) * Math.min(hw, hh);
}

function sdShape(s, px, py) {
  return s.shape === "ellipse" ? sdEllipse(px, py, s.box) : sdRectangle(px, py, s.box);
}

// Distance to a line segment. The corridor band is this, minus its half-width.
function sdSegment(px, py, a, b) {
  const vx = b[0] - a[0], vy = b[1] - a[1];
  const wx = px - a[0], wy = py - a[1];
  const len2 = vx * vx + vy * vy;
  const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, (wx * vx + wy * vy) / len2));
  return Math.hypot(wx - vx * t, wy - vy * t);
}

// A minimum that rounds off the corner where two shapes meet, so their union
// reads as one body. `k` is the width of the blend, in px.
function smoothMin(a, b, k) {
  if (k <= 0) return Math.min(a, b);
  const h = Math.max(0, Math.min(1, 0.5 + (0.5 * (b - a)) / k));
  return b * (1 - h) + a * h - k * h * (1 - h);
}
function smoothMax(a, b, k) { return -smoothMin(-a, -b, k); }

// ------------------------------------------------------------------- corridors
// A minimum spanning tree over the member centres (Prim, O(n^2) in members).
// This is what keeps a blob in one piece: without it, two members further apart
// than the padding would each get their own island.
function spanningSegments(centres) {
  const segs = [];
  if (centres.length < 2) return segs;
  const reached = [0];
  const remaining = new Set(centres.map((_, i) => i).slice(1));
  while (remaining.size) {
    let bestFrom = -1, bestTo = -1, best = Infinity;
    for (const from of reached) for (const to of remaining) {
      const a = centres[from], b = centres[to];
      const d = Math.hypot(b[0] - a[0], b[1] - a[1]);
      if (d < best) { best = d; bestFrom = from; bestTo = to; }
    }
    segs.push([centres[bestFrom], centres[bestTo]]);
    reached.push(bestTo);
    remaining.delete(bestTo);
  }
  return segs;
}

const MAX_DETOURS = 3;   // how often one corridor may bend to get out of the way

function boxCorners(b) {
  return [[b.x, b.y], [b.x + b.width, b.y],
          [b.x + b.width, b.y + b.height], [b.x, b.y + b.height]];
}
function boxCentre(b) { return [b.x + b.width / 2, b.y + b.height / 2]; }

function closestOnSegment(p, a, b) {
  const vx = b[0] - a[0], vy = b[1] - a[1];
  const len2 = vx * vx + vy * vy;
  if (len2 === 0) return a;
  const t = Math.max(0, Math.min(1,
    ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / len2));
  return [a[0] + vx * t, a[1] + vy * t];
}

// How far along `dir` a waypoint must go to leave `shape` behind: past its
// furthest corner, plus the margin.
function offsetPastShape(from, dir, shape, margin) {
  let furthest = 0;
  for (const c of boxCorners(shape.box))
    furthest = Math.max(furthest,
      (c[0] - from[0]) * dir[0] + (c[1] - from[1]) * dir[1]);
  return furthest + margin;
}

// A corridor drawn straight through a node the blob must dodge gets cut in half
// by the subtraction, and the blob falls into two pieces. So bend it: take the
// obstacle it passes closest to, step sideways past that obstacle's furthest
// corner on whichever side is nearer, and route through that waypoint.
function routeCorridor(a, b, obstacles, margin, depth) {
  depth = depth || 0;
  if (depth >= MAX_DETOURS || !obstacles.length) return [a, b];
  let blocker = null, blockedAt = a, leastSlack = 0;
  for (const s of obstacles) {
    const near = closestOnSegment(boxCentre(s.box), a, b);
    const slack = sdShape(s, near[0], near[1]) - margin;
    if (slack < leastSlack) { leastSlack = slack; blocker = s; blockedAt = near; }
  }
  if (!blocker) return [a, b];
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const len = Math.hypot(dx, dy) || 1;
  const sideways = [-dy / len, dx / len], other = [dy / len, -dx / len];
  const forward = offsetPastShape(blockedAt, sideways, blocker, margin);
  const backward = offsetPastShape(blockedAt, other, blocker, margin);
  const dir = forward <= backward ? sideways : other;
  const off = Math.min(forward, backward);
  const way = [blockedAt[0] + dir[0] * off, blockedAt[1] + dir[1] * off];
  const first = routeCorridor(a, way, obstacles, margin, depth + 1);
  const second = routeCorridor(way, b, obstacles, margin, depth + 1);
  return first.slice(0, -1).concat(second);
}

function corridorSegments(members, obstacles, margin) {
  const out = [];
  const centres = members.map(m => boxCentre(m.box));
  for (const [from, to] of spanningSegments(centres)) {
    const path = routeCorridor(from, to, obstacles, margin);
    for (let i = 0; i < path.length - 1; i++) out.push([path[i], path[i + 1]]);
  }
  return out;
}

// Distance from a point to a box, 0 inside.
function boxGap(b, x0, y0, x1, y1) {
  const dx = Math.max(b.x - x1, x0 - (b.x + b.width), 0);
  const dy = Math.max(b.y - y1, y0 - (b.y + b.height), 0);
  return Math.hypot(dx, dy);
}

// The subset of members, corridors and obstacles that can affect a tile.
function prunePieces(pieces, x0, y0, x1, y1) {
  const memberReach = BLOB.padding + BLOB.smoothing;
  const linkReach = BLOB.corridor + BLOB.smoothing;
  const avoidReach = BLOB.clearance + BLOB.smoothing;
  let members = pieces.members.filter(m => boxGap(m.box, x0, y0, x1, y1) <= memberReach);
  if (!members.length) {
    // Every member is far: the field is positive here whichever one we seed
    // with, but the smooth minimum needs one, so take the nearest.
    let best = pieces.members[0], bestGap = Infinity;
    pieces.members.forEach(m => {
      const g = boxGap(m.box, x0, y0, x1, y1);
      if (g < bestGap) { bestGap = g; best = m; }
    });
    members = [best];
  }
  const links = pieces.links.filter(([a, b]) => {
    const box = { x: Math.min(a[0], b[0]), y: Math.min(a[1], b[1]),
                  width: Math.abs(a[0] - b[0]), height: Math.abs(a[1] - b[1]) };
    return boxGap(box, x0, y0, x1, y1) <= linkReach;
  });
  const avoid = pieces.avoid.filter(s => boxGap(s.box, x0, y0, x1, y1) <= avoidReach);
  return [members, links, avoid];
}

// The scalar field whose zero contour is the blob boundary.
function makeField(members, links, avoid) {
  // Subtraction uses a tighter blend than the union: too soft and an avoided
  // node dents the boundary from much further away than its clearance.
  const cut = BLOB.smoothing / 2;
  const first = members[0], rest = members.slice(1);
  return (px, py) => {
    // Seeded with the first member, not with infinity: a smooth minimum blends
    // its two arguments, and infinity would poison the blend.
    let d = sdShape(first, px, py) - BLOB.padding;
    for (const m of rest)
      d = smoothMin(d, sdShape(m, px, py) - BLOB.padding, BLOB.smoothing);
    for (const [a, b] of links)
      d = smoothMin(d, sdSegment(px, py, a, b) - BLOB.corridor, BLOB.smoothing);
    for (const s of avoid)
      d = smoothMax(d, -(sdShape(s, px, py) - BLOB.clearance), cut);
    return d;
  };
}

// --------------------------------------------------------- marching squares
// Each contour point sits on one grid edge and is named by that edge ("h3,7"),
// not by its coordinates, so two neighbouring cells agree on it exactly and
// joining segments into loops is bookkeeping rather than guesswork.
function traceContour(pieces, bounds, resolution) {
  const cols = Math.max(2, Math.ceil((bounds.maxX - bounds.minX) / resolution) + 1);
  const rows = Math.max(2, Math.ceil((bounds.maxY - bounds.minY) / resolution) + 1);
  const values = new Float64Array(cols * rows);
  // Sample tile by tile against a pruned field. A member more than
  // padding + smoothing away from the tile can only ever return a large positive
  // distance, so it never wins the smooth minimum inside it; an avoided shape
  // beyond clearance + smoothing likewise cannot dent the boundary there. This
  // is exact, not an approximation — those terms are provably inert.
  for (let tj = 0; tj < rows; tj += BLOB_TILE) {
    for (let ti = 0; ti < cols; ti += BLOB_TILE) {
      const x0 = bounds.minX + ti * resolution, y0 = bounds.minY + tj * resolution;
      const iEnd = Math.min(cols, ti + BLOB_TILE), jEnd = Math.min(rows, tj + BLOB_TILE);
      const x1 = bounds.minX + (iEnd - 1) * resolution;
      const y1 = bounds.minY + (jEnd - 1) * resolution;
      const field = makeField(...prunePieces(pieces, x0, y0, x1, y1));
      for (let j = tj; j < jEnd; j++)
        for (let i = ti; i < iEnd; i++)
          values[j * cols + i] = field(bounds.minX + i * resolution,
                                       bounds.minY + j * resolution);
    }
  }

  const at = (i, j) => values[j * cols + i];
  const inside = (i, j) => at(i, j) < 0;
  const crossH = (i, j) => {
    const v0 = at(i, j), v1 = at(i + 1, j);
    const t = v0 === v1 ? 0.5 : v0 / (v0 - v1);
    return [bounds.minX + (i + t) * resolution, bounds.minY + j * resolution];
  };
  const crossV = (i, j) => {
    const v0 = at(i, j), v1 = at(i, j + 1);
    const t = v0 === v1 ? 0.5 : v0 / (v0 - v1);
    return [bounds.minX + i * resolution, bounds.minY + (j + t) * resolution];
  };

  const points = new Map(), segments = [];
  const link = (a, pa, b, pb) => {
    points.set(a, pa); points.set(b, pb); segments.push([a, b]);
  };
  for (let j = 0; j < rows - 1; j++) {
    for (let i = 0; i < cols - 1; i++) {
      const code = (inside(i, j) ? 1 : 0) | (inside(i + 1, j) ? 2 : 0) |
                   (inside(i + 1, j + 1) ? 4 : 0) | (inside(i, j + 1) ? 8 : 0);
      if (code === 0 || code === 15) continue;
      const topId = `h${i},${j}`, bottomId = `h${i},${j + 1}`;
      const leftId = `v${i},${j}`, rightId = `v${i + 1},${j}`;
      switch (code) {
        case 1: case 14: link(topId, crossH(i, j), leftId, crossV(i, j)); break;
        case 2: case 13: link(topId, crossH(i, j), rightId, crossV(i + 1, j)); break;
        case 3: case 12: link(leftId, crossV(i, j), rightId, crossV(i + 1, j)); break;
        case 4: case 11: link(rightId, crossV(i + 1, j), bottomId, crossH(i, j + 1)); break;
        case 6: case 9:  link(topId, crossH(i, j), bottomId, crossH(i, j + 1)); break;
        case 7: case 8:  link(leftId, crossV(i, j), bottomId, crossH(i, j + 1)); break;
        // Ambiguous: opposite corners inside. The centre value decides, which is
        // the standard fix and keeps the contour closed.
        case 5: case 10: {
          const centre = (at(i, j) + at(i + 1, j) + at(i + 1, j + 1) + at(i, j + 1)) / 4;
          if (centre < 0 ? code === 5 : code === 10) {
            link(topId, crossH(i, j), rightId, crossV(i + 1, j));
            link(leftId, crossV(i, j), bottomId, crossH(i, j + 1));
          } else {
            link(topId, crossH(i, j), leftId, crossV(i, j));
            link(rightId, crossV(i + 1, j), bottomId, crossH(i, j + 1));
          }
          break;
        }
      }
    }
  }

  // Every contour point lies on a grid edge shared by two cells, so exactly two
  // segments meet there: walking from any segment traces a whole loop.
  const adjacency = new Map();
  segments.forEach(([a, b], index) => {
    for (const id of [a, b]) {
      const list = adjacency.get(id);
      if (list) list.push(index); else adjacency.set(id, [index]);
    }
  });
  const used = new Set(), loops = [];
  for (let start = 0; start < segments.length; start++) {
    if (used.has(start)) continue;
    const ids = [segments[start][0]];
    let current = start, currentId = ids[0];
    for (;;) {
      used.add(current);
      const seg = segments[current];
      const nextId = seg[0] === currentId ? seg[1] : seg[0];
      if (nextId === ids[0]) break;
      ids.push(nextId);
      const next = (adjacency.get(nextId) || []).find(i => !used.has(i));
      if (next === undefined) break;   // contour ran off the grid; keep what we have
      current = next; currentId = nextId;
    }
    if (ids.length >= 3) loops.push(ids.map(id => points.get(id)));
  }
  return loops;
}

// ------------------------------------------------------------ simplification
function perpendicularDistance(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const len = Math.hypot(dx, dy);
  if (len === 0) return Math.hypot(p[0] - a[0], p[1] - a[1]);
  return Math.abs(dx * (a[1] - p[1]) - dy * (a[0] - p[0])) / len;
}

// Ramer-Douglas-Peucker, iterative so a long contour cannot blow the stack.
function douglasPeucker(points, tolerance) {
  if (points.length < 3) return points.slice();
  const keep = new Uint8Array(points.length);
  keep[0] = 1; keep[points.length - 1] = 1;
  const stack = [[0, points.length - 1]];
  while (stack.length) {
    const [first, last] = stack.pop();
    let worst = -1, worstD = tolerance;
    for (let i = first + 1; i < last; i++) {
      const d = perpendicularDistance(points[i], points[first], points[last]);
      if (d > worstD) { worstD = d; worst = i; }
    }
    if (worst !== -1) { keep[worst] = 1; stack.push([first, worst], [worst, last]); }
  }
  return points.filter((_, i) => keep[i] === 1);
}

function signedArea(loop) {
  let sum = 0;
  for (let i = 0, j = loop.length - 1; i < loop.length; j = i++)
    sum += (loop[j][0] - loop[i][0]) * (loop[j][1] + loop[i][1]);
  return sum / 2;
}

function containsPoint(loop, p) {
  let inside = false;
  for (let i = 0, j = loop.length - 1; i < loop.length; j = i++) {
    const [xi, yi] = loop[i], [xj, yj] = loop[j];
    if ((yi > p[1]) !== (yj > p[1]) &&
        p[0] < ((xj - xi) * (p[1] - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

// The tracing order depends on which cell the walk started in, and that decides
// which points simplification keeps. Anchoring the start to a geometric feature
// (leftmost point, ties on y) makes the output depend on the shape alone.
function rotateToExtreme(loop) {
  let best = 0;
  for (let i = 1; i < loop.length; i++)
    if (loop[i][0] < loop[best][0] ||
        (loop[i][0] === loop[best][0] && loop[i][1] < loop[best][1])) best = i;
  return loop.slice(best).concat(loop.slice(0, best));
}

function finishLoop(loop) {
  const anchored = rotateToExtreme(loop);
  const open = anchored.concat([anchored[0]]);
  // A drag traces on a coarser grid, so it has fewer real points to keep;
  // holding the full budget there would only preserve the grid's own steps.
  const maxPoints = blobDragging ? BLOB.maxPoints * 0.6 : BLOB.maxPoints;
  let simplified = douglasPeucker(open, BLOB.tolerance);
  let attempt = BLOB.tolerance;      // coarsen rather than emit hundreds of points
  while (simplified.length > maxPoints && attempt < 512) {
    attempt *= 1.6;
    simplified = douglasPeucker(open, attempt);
  }
  return simplified.slice(0, -1);
}

// --------------------------------------------------------------- entry point
// A smooth minimum is not associative, so folding members in a different order
// would move the boundary by a fraction of a pixel. A hyperedge is a *set*, so
// order it canonically first and the blob depends on the set alone.
function blobShapes(slugs, pos) {
  const out = [];
  slugs.forEach(s => {
    const p = pos[s];
    if (!p) return;
    const d = dimsOf(s), circle = styleFor(bySlug[s]) === "circle";
    out.push({ shape: circle ? "ellipse" : "rectangle",
               box: { x: p.x - d.w / 2, y: p.y - d.h / 2, width: d.w, height: d.h } });
  });
  return out.sort((a, b) => a.box.x - b.box.x || a.box.y - b.box.y ||
                            a.box.width - b.box.width || a.box.height - b.box.height);
}

// Closed outlines around `members`, largest first, in world coordinates.
// Normally there is exactly one. There can be more when an avoided node cuts a
// blob in two; loops *inside* another loop are holes and get dropped.
function blobOutline(members, avoid, sampleCap) {
  if (!members.length) return [];
  const links = corridorSegments(members, avoid, BLOB.clearance + BLOB.corridor);
  // A drag keeps the real field — the shape it makes is the whole point — and
  // pays for the frame rate with a coarser grid instead of with a convex hull.
  // Sampling is quadratic in the pitch, so 2.5x here is about 1/6 of the work.
  const pitch = BLOB.resolution * (blobDragging ? BLOB.dragCoarsen : 1);
  // The field is positive everywhere outside this margin, which keeps the
  // contour off the edge of the grid and so keeps every loop closed. It is three
  // cells of whatever pitch this pass uses, so a coarse pass stays closed too.
  const margin = BLOB.padding + BLOB.corridor + BLOB.smoothing + pitch * 3;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const { box } of members) {
    minX = Math.min(minX, box.x); minY = Math.min(minY, box.y);
    maxX = Math.max(maxX, box.x + box.width); maxY = Math.max(maxY, box.y + box.height);
  }
  for (const seg of links) for (const [x, y] of seg) {
    minX = Math.min(minX, x); minY = Math.min(minY, y);
    maxX = Math.max(maxX, x); maxY = Math.max(maxY, y);
  }
  const bounds = { minX: minX - margin, minY: minY - margin,
                   maxX: maxX + margin, maxY: maxY + margin };

  // Only shapes reaching into the grid can bend the boundary; the rest have
  // zero influence there, so dropping them changes nothing.
  const reach = BLOB.clearance + BLOB.smoothing;
  const near = avoid.filter(({ box }) =>
    box.x - reach <= bounds.maxX && box.x + box.width + reach >= bounds.minX &&
    box.y - reach <= bounds.maxY && box.y + box.height + reach >= bounds.minY);

  let resolution = pitch;
  const cap = Math.max(4000, Math.min(BLOB_MAX_SAMPLES, sampleCap || BLOB_MAX_SAMPLES));
  const samples = ((bounds.maxX - bounds.minX) / resolution + 1) *
                  ((bounds.maxY - bounds.minY) / resolution + 1);
  if (samples > cap) resolution *= Math.sqrt(samples / cap);

  const loops = traceContour({ members, links, avoid: near }, bounds, resolution);
  // Even-odd nesting: a loop inside an odd number of others is a hole.
  return loops
    .filter((loop, i) => loops.reduce(
      (depth, other, j) => depth + (j !== i && containsPoint(other, loop[0]) ? 1 : 0),
      0) % 2 === 0)
    .map(finishLoop)
    .filter(loop => loop.length >= 4)
    .sort((a, b) => Math.abs(signedArea(b)) - Math.abs(signedArea(a)));
}

// Non-members the blob has to bend around: every other node in the layout.
// Read from `pos`, not from the drawn elements — the blob layer is built before
// the node layer, so `nodeEls` still holds the *previous* render at this point
// (and nothing at all on the first one, which silently disabled avoidance).
//
// At 500 nodes and 59 blobs, handing every blob all 499 non-members and letting
// blobOutline filter them is 30,000 box tests per render before any sampling
// starts. A spatial hash over the node boxes, built once per render, answers
// "which non-members reach into this blob's span?" directly.
//
// `posEpoch` is in the key because a drag mutates `pos` in place: the node count
// and the layout signature both stay exactly what they were, so without it a
// node dragged into a cluster would never become an obstacle for that cluster.
let _avoidGrid = null, _avoidGridKey = "";
function avoidGrid(pos) {
  const key = Object.keys(pos).length + ":" + posEpoch + ":" + layoutKey();
  if (_avoidGrid && _avoidGridKey === key) return _avoidGrid;
  const items = [];
  for (const slug in pos) {
    if (!bySlug[slug]) continue;
    const p = pos[slug], d = dimsOf(slug);
    items.push({ slug, minX: p.x - d.w / 2, maxX: p.x + d.w / 2,
                 minY: p.y - d.h / 2, maxY: p.y + d.h / 2 });
  }
  _avoidGridKey = key;
  _avoidGrid = gridHash(items, Math.max(NW, BW, 120));
  return _avoidGrid;
}

function blobAvoidShapes(memberSet, pos) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  memberSet.forEach(slug => {
    const p = pos[slug];
    if (!p) return;
    const d = dimsOf(slug);
    minX = Math.min(minX, p.x - d.w / 2); maxX = Math.max(maxX, p.x + d.w / 2);
    minY = Math.min(minY, p.y - d.h / 2); maxY = Math.max(maxY, p.y + d.h / 2);
  });
  if (!isFinite(minX)) return [];
  const reach = BLOB.padding + BLOB.corridor + BLOB.smoothing + BLOB.clearance + 40;
  const others = [];
  avoidGrid(pos).near(minX - reach, minY - reach, maxX + reach, maxY + reach)
    .forEach(it => { if (!memberSet.has(it.slug)) others.push(it.slug); });
  return blobShapes(others, pos);
}

// True when the distance field is worth computing. Only the zoom decides: below
// BLOB_FIELD_MIN_ZOOM the field's detail cannot be seen, so the cheap hull is
// honest there. A drag stays on the field and coarsens the grid instead —
// swapping in the hull mid-drag replaced the shape with a much larger one, which
// read as the blob breaking rather than as a deliberate saving.
let blobDragging = false;
function blobFieldMode() {
  return tfFor().k >= BLOB_FIELD_MIN_ZOOM;
}

// Cached per hyperedge so a re-render (theme flip, dim pass) does not recompute
// the field. Keyed by the positions the field was built from — *and* by
// `posEpoch`, because the outline also depends on where the non-members are:
// dragging one of those through a blob leaves every member position untouched,
// and a member-only key would then hand back the pre-drag shape.
const blobCache = new Map();
function blobGeometry(h, pos) {
  const key = posEpoch + "|" + h.state + "|" + h.members.map(s => {
    const p = pos[s];
    return p ? Math.round(p.x) + "," + Math.round(p.y) : "-";
  }).join(";");
  const hit = blobCache.get(h.state);
  if (hit && hit.key === key) return hit.value;
  const memberSet = new Set(h.members);
  const share = BLOB_SAMPLE_BUDGET / Math.max(1, hyperedges().list.length);
  const value = blobOutline(blobShapes(h.members, pos),
                            blobAvoidShapes(memberSet, pos), share);
  blobCache.set(h.state, { key, value });
  return value;
}

// The path for one hyperedge: field loops when they are worth it, hull if not.
function blobPathFor(h, pos) {
  if (!blobFieldMode()) return blobPath(h.members, pos);
  const loops = blobGeometry(h, pos);
  if (!loops.length) return blobPath(h.members, pos);
  return loops.map(closedCurve).filter(Boolean).join(" ") || blobPath(h.members, pos);
}

// -------------------------------------------------------------- blob labels
// Placed *on* the outline rather than pushed up off it (excaligraph's
// top | centre | bottom idea): each label takes the first anchor that does not
// collide with one already placed, so a dense cluster spreads its labels around
// its own boundary instead of drifting into a stack above the canvas.
function outlineAnchors(loops, members, pos) {
  if (loops && loops.length) {
    const loop = loops[0];
    let minY = Infinity, maxY = -Infinity, sumX = 0;
    loop.forEach(p => { minY = Math.min(minY, p[1]); maxY = Math.max(maxY, p[1]); sumX += p[0]; });
    const near = (target, sign) => {
      let x = 0, n = 0;
      loop.forEach(p => { if (Math.abs(p[1] - target) < 6) { x += p[0]; n++; } });
      return { x: n ? x / n : sumX / loop.length, y: target + sign * 12 };
    };
    return [near(minY, -1), near(maxY, 1),
            { x: sumX / loop.length, y: (minY + maxY) / 2 }];
  }
  const pts = members.flatMap(s => memberOutline(s, pos));
  if (!pts.length) return [{ x: 0, y: 0 }];
  let cx = 0, top = 1e9, bottom = -1e9;
  pts.forEach(p => { cx += p.x; top = Math.min(top, p.y); bottom = Math.max(bottom, p.y); });
  cx /= pts.length;
  return [{ x: cx, y: top - BPAD - 8 }, { x: cx, y: bottom + BPAD + 14 },
          { x: cx, y: (top + bottom) / 2 }];
}

// Anchoring every label reads every outline, and a drag repaints one or two
// blobs — computing the other twelve fields to place labels that are not moving
// would cost more than the drag itself. So a drag anchors on whatever geometry
// each blob last had; pointerup redraws the layer and the labels land exactly.
function labelLoops(h, pos) {
  if (!blobFieldMode()) return null;
  if (!blobDragging) return blobGeometry(h, pos);
  const hit = blobCache.get(h.state);
  return hit ? hit.value : null;
}

function blobLabelPositions(pos) {
  const placed = [], out = {};
  hyperedges().list.forEach(h => {
    const loops = labelLoops(h, pos);
    const anchors = outlineAnchors(loops, h.members, pos);
    const w = h.state.length * 6.3;
    const clear = c => !placed.some(p =>
      Math.abs(c.x - p.x) < (w + p.w) / 2 + 8 && Math.abs(c.y - p.y) < 13);
    let chosen = anchors.find(clear);
    if (!chosen) {  // every anchor taken: step up from the first until clear
      chosen = { x: anchors[0].x, y: anchors[0].y };
      while (!clear(chosen)) chosen.y -= 14;   // strictly decreases, so it ends
    }
    placed.push({ x: chosen.x, y: chosen.y, w });
    out[h.state] = chosen;
  });
  return out;
}

// Which blobs a node at its current position can bend, whether or not it is a
// member of them. A non-member is subtracted from the field, so moving one into
// a cluster changes that cluster's outline — the repaint during a drag has to
// cover those, not only the blobs the dragged node belongs to.
function blobsTouching(slug, pos) {
  const p = pos[slug];
  if (!p) return [];
  const d = dimsOf(slug);
  const reach = BLOB.padding + BLOB.corridor + BLOB.smoothing + BLOB.clearance + 40;
  const x0 = p.x - d.w / 2 - reach, x1 = p.x + d.w / 2 + reach;
  const y0 = p.y - d.h / 2 - reach, y1 = p.y + d.h / 2 + reach;
  const out = [];
  hyperedges().list.forEach(h => {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    h.members.forEach(m => {
      const q = pos[m];
      if (!q) return;
      const dm = dimsOf(m);
      minX = Math.min(minX, q.x - dm.w / 2); maxX = Math.max(maxX, q.x + dm.w / 2);
      minY = Math.min(minY, q.y - dm.h / 2); maxY = Math.max(maxY, q.y + dm.h / 2);
    });
    if (isFinite(minX) && minX <= x1 && maxX >= x0 && minY <= y1 && maxY >= y0)
      out.push(h.state);
  });
  return out;
}
