// ---------------------------------------------------------------- quadtree
// Barnes-Hut. The pairwise repulsion loop is the only thing on this page that
// scales badly: at 500 nodes it is 240 ticks x 125,000 pairs = 30 million
// distance computations before the first paint. A quadtree collapses every
// distant clump of nodes into one body, which turns the tick from O(n^2) into
// O(n log n) and leaves the near field — the part that actually shapes the
// drawing — computed exactly.
//
// Deterministic, like everything else here: the tree is built in a fixed order
// and walked with an explicit stack, so the same input gives the same forces.

const QT_THETA = 0.9;      // cell size / distance below this: treat as one body
const QT_MAX_DEPTH = 20;   // coincident points would subdivide forever otherwise

function qtCell(x, y, size) {
  return { x, y, size, mass: 0, sx: 0, sy: 0, cx: 0, cy: 0,
           slug: null, px: 0, py: 0, kids: null };
}

function qtPlace(c, slug, x, y, depth) {
  const h = c.size / 2;
  const i = (x >= c.x + h ? 1 : 0) + (y >= c.y + h ? 2 : 0);
  const kid = c.kids[i] ||
    (c.kids[i] = qtCell(c.x + ((i & 1) ? h : 0), c.y + ((i & 2) ? h : 0), h));
  qtInsert(kid, slug, x, y, depth + 1);
}

function qtInsert(c, slug, x, y, depth) {
  c.mass += 1; c.sx += x; c.sy += y;
  c.cx = c.sx / c.mass; c.cy = c.sy / c.mass;
  if (c.mass === 1) { c.slug = slug; c.px = x; c.py = y; return; }
  if (depth >= QT_MAX_DEPTH) return;   // give up subdividing; the cell lumps them
  if (!c.kids) {
    c.kids = [null, null, null, null];
    if (c.slug !== null) { qtPlace(c, c.slug, c.px, c.py, depth); c.slug = null; }
  }
  qtPlace(c, slug, x, y, depth);
}

function quadtree(slugs, pos) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const s of slugs) {
    const p = pos[s];
    if (!p) continue;
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.y > maxY) maxY = p.y;
  }
  if (!isFinite(minX)) return null;
  const size = Math.max(maxX - minX, maxY - minY, 1) * 1.05;
  const root = qtCell(minX, minY, size);
  for (const s of slugs) if (pos[s]) qtInsert(root, s, pos[s].x, pos[s].y, 0);
  return root;
}

// Repulsion on one node, accumulated into `f`. Same law as the exact loop —
// min(cap, strength / d^2) — so tuning carries over unchanged; a lumped cell
// simply contributes its own mass times that.
function qtRepulsion(root, slug, x, y, strength, cap, f) {
  if (!root) return;
  const stack = [root];
  while (stack.length) {
    const c = stack.pop();
    if (!c || !c.mass) continue;
    const single = c.kids === null && c.mass === 1;
    if (single && c.slug === slug) continue;
    let dx = x - c.cx, dy = y - c.cy, d2 = dx * dx + dy * dy;
    if (d2 < 1e-4) {  // coincident: deterministic symmetry break, as before
      const ang = hashSlug(slug + (c.slug || "cell")) * 6.283185307;
      dx = Math.cos(ang); dy = Math.sin(ang); d2 = 1;
    }
    if (!single && c.kids && c.size * c.size >= QT_THETA * QT_THETA * d2) {
      for (let i = 0; i < 4; i++) if (c.kids[i]) stack.push(c.kids[i]);
      continue;
    }
    const d = Math.sqrt(d2);
    const rep = Math.min(cap, strength / d2) * (single ? 1 : c.mass);
    f.x += (dx / d) * rep;
    f.y += (dy / d) * rep;
  }
}

// ------------------------------------------------------------ spatial hash
// A uniform grid over the same points. Cheaper than a tree when the query is
// "what is near this box?" rather than "what is the aggregate force here?" —
// which is what card de-overlap and blob avoidance both ask.
function gridHash(items, cellSize) {
  const buckets = new Map();
  const key = (i, j) => i + "," + j;
  items.forEach(it => {
    const i0 = Math.floor(it.minX / cellSize), i1 = Math.floor(it.maxX / cellSize);
    const j0 = Math.floor(it.minY / cellSize), j1 = Math.floor(it.maxY / cellSize);
    for (let i = i0; i <= i1; i++) for (let j = j0; j <= j1; j++) {
      const k = key(i, j);
      const bucket = buckets.get(k);
      if (bucket) bucket.push(it); else buckets.set(k, [it]);
    }
  });
  return {
    cellSize,
    near(minX, minY, maxX, maxY) {
      const out = new Set();
      const i0 = Math.floor(minX / cellSize), i1 = Math.floor(maxX / cellSize);
      const j0 = Math.floor(minY / cellSize), j1 = Math.floor(maxY / cellSize);
      for (let i = i0; i <= i1; i++) for (let j = j0; j <= j1; j++) {
        const bucket = buckets.get(key(i, j));
        if (bucket) bucket.forEach(it => out.add(it));
      }
      return out;
    },
  };
}
