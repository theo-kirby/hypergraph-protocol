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

// FNV-1a -> [0,1): the page's only source of jitter, and it is a pure
// function of the slug — so every load lays out identically.
function hashSlug(s) {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h / 4294967296;
}

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

function simTick(pos, nodes, springs, homes, alpha) {
  const f = {};
  nodes.forEach(s => f[s] = { x: 0, y: 0 });
  for (let i = 0; i < nodes.length; i++) {          // pairwise repulsion
    for (let j = i + 1; j < nodes.length; j++) {
      const a = pos[nodes[i]], b = pos[nodes[j]];
      let dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy;
      if (d2 < 1e-4) {  // coincident: deterministic symmetry break
        const ang = hashSlug(nodes[i] + nodes[j]) * 6.283185307;
        dx = Math.cos(ang); dy = Math.sin(ang); d2 = 1;
      }
      const d = Math.sqrt(d2), rep = Math.min(30, 20000 / d2);
      const ux = dx / d, uy = dy / d;
      f[nodes[i]].x += ux * rep; f[nodes[i]].y += uy * rep;
      f[nodes[j]].x -= ux * rep; f[nodes[j]].y -= uy * rep;
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
function runSim(pos, homes) {
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
  let alpha = 1.0;
  for (let t = 0; t < NODE_TICKS; t++) {
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
