function simTick(pos, nodes, springs, clusters, alpha) {
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
      const d = Math.sqrt(d2), rep = Math.min(30, 24000 / d2);
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
  clusters.forEach(ms => {                          // hyperedge members cohere
    if (ms.length < 2) return;
    let cx = 0, cy = 0;
    ms.forEach(s => { cx += pos[s].x; cy += pos[s].y; });
    cx /= ms.length; cy /= ms.length;
    ms.forEach(s => {
      f[s].x += (cx - pos[s].x) * 0.08;
      f[s].y += (cy - pos[s].y) * 0.08;
    });
  });
  nodes.forEach(s => {                              // mild centering + integrate
    f[s].x -= pos[s].x * 0.005;
    f[s].y -= pos[s].y * 0.005;
    pos[s].x += f[s].x * alpha;
    pos[s].y += f[s].y * alpha;
  });
}

// Springs come from graph *structure* (parent edges + cross-links), never from
// the edge display toggles, so the layout is stable under checkbox flips.
// Node iteration order is DATA array order (record then state): deterministic.
function runSim(pos) {
  const nodes = [];
  const springs = [];
  const tree = g => DATA[g].nodes.forEach(n => {
    nodes.push(n.slug);
    n.parents.forEach(p => { if (pos[p]) springs.push([p, n.slug, 0.03, 110]); });
  });
  if (recVis()) tree("record");
  if (stVis()) tree("state");
  if (recVis() && stVis()) DATA.links.forEach(l => {
    if (pos[l.record] && pos[l.state])
      springs.push([l.record, l.state, 0.012, 170]);
  });
  const clusters = hyperedges().list.map(h => {
    const ms = h.members.filter(s => pos[s]);
    if (pos[h.state]) ms.push(h.state);  // blobs settle near their state node
    return ms;
  });
  let alpha = 1.0;
  for (let t = 0; t < 300; t++) {
    simTick(pos, nodes, springs, clusters, alpha);
    alpha *= 0.985;
  }
}

