// x offset of the state column in the layered two-column arrangement; also
// anchors the column header texts.
function comboStateX() { return show.style === "cards" ? NW + 430 : 300; }

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
      DATA.record.nodes.forEach(n => pos[n.slug] = { x: 0, y: n.seq * rStep });
      DATA.state.nodes.forEach(n => pos[n.slug] = { x: sx, y: n.seq * sStep });
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
  } else {                         // force: deterministic seed + sim
    let maxOrder = 0;
    if (recVis()) DATA.record.nodes.forEach(n => {
      maxOrder = Math.max(maxOrder, n.order);
      pos[n.slug] = {
        x: n.order * 80 + (hashSlug(n.slug) - 0.5) * 8,
        y: n.layer * 80 + (hashSlug(n.slug + "y") - 0.5) * 8,
      };
    });
    if (stVis()) DATA.state.nodes.forEach(n => pos[n.slug] = {
      x: (maxOrder + 3) * 80 + n.order * 80 + (hashSlug(n.slug) - 0.5) * 8,
      y: n.layer * 80 + (hashSlug(n.slug + "y") - 0.5) * 8,
    });
    runSim(pos);
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

