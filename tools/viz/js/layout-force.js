// ------------------------------------------------------------------- force
// The Clusters view asks one question: which record work belongs to the same
// state claim? A single flat force sim answers it badly — every node repels
// every other equally, so twelve hyperedges settle into one overlapping pile and
// the blobs on top of them become mush.
//
// So the layout runs at two levels. First the *hyperedges* are laid out as a
// coarse graph of twelve bodies, each with a radius set by its member count,
// pushed apart until they no longer overlap and pulled together when they share
// members. Only then do nodes settle, each held near the centre of the
// hyperedge(s) it belongs to. Group separation is decided by the level that
// knows about groups, which is what makes it hold.

const CLUSTER_GAP = 34;        // clear space demanded between two hyperedges
const CLUSTER_TICKS = 260, NODE_TICKS = 240;
// Below this the exact pairwise loop is cheaper than building a tree per tick,
// and it stays as the reference the approximation is tested against.
const BH_MIN_NODES = 120;

// Jitter throughout this file comes from `hashSlug` (core.js): FNV-1a of the
// slug, so every load lays out identically. It used to be declared here too,
// with an identical body — two hoisted declarations in one scope, where the
// later one silently won. The seeded copy in core.js is now the only one.

// Radius a hyperedge needs to hold its members without crowding them.
function clusterRadius(h) {
  return 40 + 26 * Math.sqrt(Math.max(1, h.members.length));
}

// Coarse layout over the hyperedges themselves. Seeded on a ring ordered by
// size (biggest first) so the result is reproducible and the large clusters,
// which have the least freedom, claim their space first.
function clusterCentres() {
  const list = hyperedges().list;
  if (!list.length) return {};
  const order = list.slice().sort((a, b) => b.members.length - a.members.length ||
                                            (a.state < b.state ? -1 : 1));
  const radius = {}, centre = {};
  order.forEach((h, i) => {
    radius[h.state] = clusterRadius(h);
    const angle = (i / order.length) * 6.283185307 + hashSlug(h.state) * 0.4;
    const ring = 60 + 46 * Math.sqrt(order.length) * (0.7 + 0.3 * (i / order.length));
    centre[h.state] = { x: Math.cos(angle) * ring, y: Math.sin(angle) * ring };
  });

  // Shared members pull two hyperedges together; overlap pushes them apart.
  const shared = [];
  for (let i = 0; i < order.length; i++) {
    const mi = new Set(order[i].members);
    for (let j = i + 1; j < order.length; j++) {
      const n = order[j].members.reduce((c, m) => c + (mi.has(m) ? 1 : 0), 0);
      if (n) shared.push([order[i].state, order[j].state, n]);
    }
  }

  for (let t = 0; t < CLUSTER_TICKS; t++) {
    const alpha = 1 - t / CLUSTER_TICKS;
    shared.forEach(([a, b, n]) => {
      const pa = centre[a], pb = centre[b];
      const dx = pb.x - pa.x, dy = pb.y - pa.y;
      const d = Math.hypot(dx, dy) || 1;
      const rest = radius[a] + radius[b] + CLUSTER_GAP;
      const pull = Math.min(0.06, 0.012 * n) * (d - rest) / d * alpha;
      pa.x += dx * pull; pa.y += dy * pull;
      pb.x -= dx * pull; pb.y -= dy * pull;
    });
    for (let i = 0; i < order.length; i++) {
      for (let j = i + 1; j < order.length; j++) {
        const a = order[i].state, b = order[j].state;
        const pa = centre[a], pb = centre[b];
        let dx = pb.x - pa.x, dy = pb.y - pa.y;
        let d = Math.hypot(dx, dy);
        if (d < 1e-3) {  // coincident: deterministic symmetry break
          const ang = hashSlug(a + b) * 6.283185307;
          dx = Math.cos(ang); dy = Math.sin(ang); d = 1;
        }
        const want = radius[a] + radius[b] + CLUSTER_GAP;
        if (d >= want) continue;
        const push = ((want - d) / d) * 0.5;
        pa.x -= dx * push; pa.y -= dy * push;
        pb.x += dx * push; pb.y += dy * push;
      }
    }
    order.forEach(h => {  // mild centering keeps the whole board near the origin
      centre[h.state].x *= 1 - 0.004 * alpha;
      centre[h.state].y *= 1 - 0.004 * alpha;
    });
  }
  return { centre, radius };
}

// Where a node wants to sit: the centre of its hyperedge, or the mean of them
// when it belongs to several — a node cited by two claims belongs between them.
function nodeHomes(centres) {
  const H = hyperedges(), homes = {};
  DATA.record.nodes.forEach(n => {
    const owners = (H.memberOf[n.slug] || []).filter(st => centres.centre[st]);
    if (!owners.length) return;
    let x = 0, y = 0;
    owners.forEach(st => { x += centres.centre[st].x; y += centres.centre[st].y; });
    homes[n.slug] = { x: x / owners.length, y: y / owners.length,
                      // a node shared by two clusters is held less tightly by
                      // either, so it can sit in the overlap rather than fight
                      weight: owners.length > 1 ? 0.10 : 0.22 };
  });
  return homes;
}

const REPULSION = 20000, REPULSION_CAP = 30;

function simTick(pos, nodes, springs, homes, alpha) {
  const f = {};
  nodes.forEach(s => f[s] = { x: 0, y: 0 });
  // Repulsion through a Barnes-Hut tree: exact near, lumped far. Below the
  // crossover the tree costs more than it saves, so small graphs keep the plain
  // pairwise loop — which is also the reference the tree is checked against.
  if (nodes.length >= BH_MIN_NODES) {
    const tree = quadtree(nodes, pos);
    nodes.forEach(s => qtRepulsion(tree, s, pos[s].x, pos[s].y,
                                   REPULSION, REPULSION_CAP, f[s]));
  } else {
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = pos[nodes[i]], b = pos[nodes[j]];
        let dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy;
        if (d2 < 1e-4) {  // coincident: deterministic symmetry break
          const ang = hashSlug(nodes[i] + nodes[j]) * 6.283185307;
          dx = Math.cos(ang); dy = Math.sin(ang); d2 = 1;
        }
        const d = Math.sqrt(d2), rep = Math.min(REPULSION_CAP, REPULSION / d2);
        const ux = dx / d, uy = dy / d;
        f[nodes[i]].x += ux * rep; f[nodes[i]].y += uy * rep;
        f[nodes[j]].x -= ux * rep; f[nodes[j]].y -= uy * rep;
      }
    }
  }
  springs.forEach(sp => {                           // [from, to, k, rest]
    const a = pos[sp[0]], b = pos[sp[1]];
    const dx = b.x - a.x, dy = b.y - a.y;
    const d = Math.sqrt(dx * dx + dy * dy) || 1;
    const k = sp[2] * (d - sp[3]) / d;
    f[sp[0]].x += dx * k; f[sp[0]].y += dy * k;
    f[sp[1]].x -= dx * k; f[sp[1]].y -= dy * k;
  });
  nodes.forEach(s => {                              // home pull + integrate
    const home = homes[s];
    if (home) {
      f[s].x += (home.x - pos[s].x) * home.weight;
      f[s].y += (home.y - pos[s].y) * home.weight;
    } else {
      f[s].x -= pos[s].x * 0.005;
      f[s].y -= pos[s].y * 0.005;
    }
    pos[s].x += f[s].x * alpha;
    pos[s].y += f[s].y * alpha;
  });
}

// Springs come from graph *structure* (parent edges + cross-links), never from
// the edge display toggles, so the layout is stable under checkbox flips.
// Node iteration order is DATA array order (record then state): deterministic.
function runSim(pos, homes, ticks, alpha0) {
  const nodes = [];
  const springs = [];
  // Parent edges pull only weakly here: in this view the grouping is the
  // message, and a strong causal chain would drag members out of their blob.
  const tree = g => DATA[g].nodes.forEach(n => {
    if (!pos[n.slug]) return;
    nodes.push(n.slug);
    n.parents.forEach(p => { if (pos[p]) springs.push([p, n.slug, 0.012, 120]); });
  });
  if (recVis()) tree("record");
  if (stVis()) tree("state");
  if (recVis() && stVis()) DATA.links.forEach(l => {
    if (pos[l.record] && pos[l.state])
      springs.push([l.record, l.state, 0.012, 170]);
  });
  let alpha = alpha0 || 1.0;
  const n = ticks || NODE_TICKS;
  for (let t = 0; t < n; t++) {
    simTick(pos, nodes, springs, homes || {}, alpha);
    alpha *= 0.985;
  }
}

// Seed members on a ring inside their cluster, in a deterministic order, so the
// sim starts already grouped and only has to relax rather than to discover.
function seedClustered(pos, centres, homes) {
  const H = hyperedges();
  const seen = {};
  H.list.forEach(h => {
    const c = centres.centre[h.state];
    if (!c) return;
    const r = centres.radius[h.state] * 0.72, n = Math.max(1, h.members.length);
    h.members.forEach((m, i) => {
      if (seen[m] || !bySlug[m]) return;
      seen[m] = true;
      // Sunflower packing: even area coverage, so a big cluster stays compact
      // instead of stringing its members around one wide ring.
      const a = i * 2.399963229728653 + hashSlug(h.state) * 6.283185307;
      const rad = r * Math.sqrt((i + 0.5) / n);
      pos[m] = { x: c.x + Math.cos(a) * rad, y: c.y + Math.sin(a) * rad };
    });
  });
  let loose = 0;
  DATA.record.nodes.forEach(n => {   // nodes no claim ever cited, on the outside
    if (pos[n.slug] || !recVis()) return;
    const a = (loose++ / 8) * 6.283185307;
    const ring = 40 + 30 * Math.sqrt(DATA.record.nodes.length);
    pos[n.slug] = { x: Math.cos(a) * ring * 1.9, y: Math.sin(a) * ring * 1.9 };
  });
  if (stVis()) DATA.state.nodes.forEach(n => {  // a state node sits in its blob
    const c = centres.centre[n.slug];
    pos[n.slug] = c ? { x: c.x, y: c.y - centres.radius[n.slug] * 0.25 }
                    : { x: (hashSlug(n.slug) - 0.5) * 300, y: -420 };
    if (c) homes[n.slug] = { x: c.x, y: c.y, weight: 0.18 };
  });
}

function layoutForce(pos) {
  const centres = clusterCentres();
  if (!centres.centre) {   // no hyperedges: plain seeded sim
    let maxOrder = 0;
    if (recVis()) DATA.record.nodes.forEach(n => {
      maxOrder = Math.max(maxOrder, n.order);
      pos[n.slug] = { x: n.order * 80 + (hashSlug(n.slug) - 0.5) * 8,
                      y: n.layer * 80 + (hashSlug(n.slug + "y") - 0.5) * 8 };
    });
    if (stVis()) DATA.state.nodes.forEach(n => pos[n.slug] = {
      x: (maxOrder + 3) * 80 + n.order * 80 + (hashSlug(n.slug) - 0.5) * 8,
      y: n.layer * 80 + (hashSlug(n.slug + "y") - 0.5) * 8 });
    runSim(pos, {});
    return pos;
  }
  const homes = nodeHomes(centres);
  seedClustered(pos, centres, homes);
  if (!recVis()) for (const s in pos) if (bySlug[s].graph === "record") delete pos[s];
  runSim(pos, homes);
  return pos;
}

// ------------------------------------------------------------------- relax
// Settle the arrangement that is on screen *now*, rather than computing a new
// one. Every home comes from the current centroid of a hyperedge's members, so
// a cluster you dragged across the canvas stays where you put it and only the
// overlaps inside it come apart. Short and cool: this is a nudge, not a redo.
// The full layout runs 240 ticks from alpha 1 and ends cold, near 0.03. Relax
// starts at 0.15 and lands in the same place, so on an already-settled drawing
// it barely moves anything — reheating past that is not settling, it is a redo
// wearing the wrong label.
const RELAX_TICKS = 90, RELAX_ALPHA = 0.15;

function relaxLayout(pos) {
  const H = hyperedges(), centre = {};
  H.list.forEach(h => {
    let x = 0, y = 0, n = 0;
    h.members.forEach(m => { const p = pos[m]; if (p) { x += p.x; y += p.y; n++; } });
    if (n) centre[h.state] = { x: x / n, y: y / n };
  });
  const homes = {};
  DATA.record.nodes.forEach(n => {
    if (!pos[n.slug]) return;
    const owners = (H.memberOf[n.slug] || []).filter(st => centre[st]);
    if (!owners.length) return;
    let x = 0, y = 0;
    owners.forEach(st => { x += centre[st].x; y += centre[st].y; });
    homes[n.slug] = { x: x / owners.length, y: y / owners.length,
                      weight: owners.length > 1 ? 0.10 : 0.22 };
  });
  DATA.state.nodes.forEach(n => {
    if (pos[n.slug] && centre[n.slug])
      homes[n.slug] = { x: centre[n.slug].x, y: centre[n.slug].y, weight: 0.18 };
  });
  // A node no claim ever cited has no home to go to, and the sim's fallback is a
  // slow pull toward the origin — over 90 ticks that walks a far-out node a few
  // hundred px, which is exactly the "it moved my thing" this button avoids. So
  // anchor it where it already is, loosely enough that overlaps still come apart.
  for (const slug in pos) if (!homes[slug])
    homes[slug] = { x: pos[slug].x, y: pos[slug].y, weight: 0.06 };
  runSim(pos, homes, RELAX_TICKS, RELAX_ALPHA);
  return pos;
}
