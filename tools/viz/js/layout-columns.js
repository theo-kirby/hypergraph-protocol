// x offset of the state column in the layered two-column arrangement; also
// anchors the column header texts.
function comboStateX() { return show.style === "cards" ? NW + 430 : 300; }

// Order for the state column: the mean chronological position of the record
// work each claim rests on. This is the barycentre sweep `layered_layout` runs
// within one graph, applied *across* the two — a claim built from early work
// sits beside early work, which is the cheapest way to cut crossings without
// hiding a single link.
//
// Claims with no provenance keep their architecture order, pinned to the top so
// the state root stays where a reader expects it.
function stateColumnOrder() {
  const chrono = {};
  DATA.record.nodes.forEach(n => chrono[n.slug] = n.chrono);
  const acc = {};
  DATA.links.forEach(l => {
    if (chrono[l.record] == null) return;
    (acc[l.state] = acc[l.state] || []).push(chrono[l.record]);
  });
  const bary = n => {
    if (n.is_root) return -2;           // the root is an anchor, not a claim
    const xs = acc[n.slug];
    if (!xs || !xs.length) return -1;   // unlinked: keep it above the rest
    return xs.reduce((a, b) => a + b, 0) / xs.length;
  };
  return DATA.state.nodes.slice()
    .sort((a, b) => bary(a) - bary(b) || a.seq - b.seq);
}

function computeLayout() {
  const pos = {};
  const cards = show.style === "cards";
  if (show.layout === "timeline") {
    return layoutTimeline(pos);
  } else if (show.layout === "board") {
    return layoutBoard(pos);
  } else if (show.layout === "layered") {
    if (show.graphs === "both") {  // two chronological columns
      const sx = comboStateX();
      const rStep = cards ? NH + 30 : 44, sStep = cards ? NH + 46 : 44;
      // The record column runs in real time order, so "further down" means
      // "later" and the state column's barycentre is measured against something
      // a reader can actually see.
      DATA.record.nodes.forEach(n => pos[n.slug] = { x: 0, y: n.chrono * rStep });
      stateColumnOrder().forEach((n, i) => pos[n.slug] = { x: sx, y: i * sStep });
    } else {                       // single graph: centered layer grid
      const g = show.graphs;
      const dx = cards ? NW + 70 : 76, dy = cards ? NH + 78 : 84;
      const perLayer = {};
      DATA[g].nodes.forEach(n => (perLayer[n.layer] = perLayer[n.layer] || []).push(n));
      DATA[g].nodes.forEach(n => {
        const width = perLayer[n.layer].length;
        pos[n.slug] = { x: (n.order - (width - 1) / 2) * dx, y: n.layer * dy };
      });
    }
  } else {                         // force: two-level cluster sim, deterministic
    layoutForce(pos);
    if (cards) {  // sim runs in circle metric; stretch, then separate any
      for (const s in pos) { pos[s].x *= 3.2; pos[s].y *= 1.8; }
      const slugs = Object.keys(pos);  // insertion order: deterministic
      const mw = NW + 24, mh = NH + 24;
      for (let pass = 0; pass < 40; pass++) {
        let any = false;
        for (let i = 0; i < slugs.length; i++) {
          for (let j = i + 1; j < slugs.length; j++) {
            const a = pos[slugs[i]], b = pos[slugs[j]];
            const ox = mw - Math.abs(a.x - b.x), oy = mh - Math.abs(a.y - b.y);
            if (ox <= 0 || oy <= 0) continue;  // cards clear of each other
            any = true;
            if (ox * mh < oy * mw) {  // push apart along the cheaper axis
              const s = (a.x <= b.x ? -1 : 1) * ox / 2;
              a.x += s; b.x -= s;
            } else {
              const s = (a.y <= b.y ? -1 : 1) * oy / 2;
              a.y += s; b.y -= s;
            }
          }
        }
        if (!any) break;
      }
    }
  }
  return pos;
}

