// Which edges exist is decided by the display toggles; how they are drawn is
// decided separately by node style + layout in edgePath.
//
// Cross-graph links are kept in their own layer, rebuilt on demand, because
// there are 176 of them over 51 nodes on this repo alone and drawing them all
// at once is the hairball the Provenance view used to be. `show.links` decides
// how many exist at all; the impact/prov checkboxes decide which kinds.
function edgesFor() {
  const out = [];
  const sided = show.graphs === "both" && show.layout === "layered";
  const tree = (g, side) => DATA[g].nodes.forEach(n =>
    n.parents.forEach(p => out.push({ kind:"tree", from:p, to:n.slug, side })));
  if (show.tree) {
    if (recVis()) tree("record", sided ? "left" : null);
    if (stVis()) tree("state", sided ? "right" : null);
  }
  return out;
}

function crossLinksFor() {
  if (show.graphs !== "both" || show.links === "none") return [];
  const focus = show.links === "focus" ? (hovered || selected) : null;
  if (show.links === "focus" && !focus) return [];
  return DATA.links.filter(l => {
    if (l.kind === "impact" ? !show.impact : !show.prov) return false;
    return !focus || l.record === focus || l.state === focus;
  }).map(l => ({
    kind: l.kind, label: l.label, state: l.state,
    from: l.kind === "impact" ? l.record : l.state,
    to:   l.kind === "impact" ? l.state : l.record,
  }));
}

// Point on the border of the w x h box centered at a, along a -> b.
function trimToRect(a, b, d) {
  const dx = b.x - a.x, dy = b.y - a.y;
  if (!dx && !dy) return { x: a.x, y: a.y };
  const tx = dx ? (d.w / 2) / Math.abs(dx) : Infinity;
  const ty = dy ? (d.h / 2) / Math.abs(dy) : Infinity;
  const t = Math.min(tx, ty);
  return { x: a.x + dx * t, y: a.y + dy * t };
}

// Timeline edges read like `git log --graph`: out of the parent's right edge,
// into the child's left edge, with the bend held near the child so a lane change
// is visible as a hook rather than a long diagonal.
function timelineEdgePath(a, b, da, db) {
  const x1 = a.x + da.w / 2, x2 = b.x - db.w / 2;
  if (x2 <= x1) {  // same column or backwards: a shallow arc under the lanes
    const my = Math.max(a.y, b.y) + LANE_H * 0.55;
    return `M ${a.x} ${a.y + da.h / 2} C ${a.x} ${my}, ${b.x} ${my}, ${b.x} ${b.y + db.h / 2}`;
  }
  const bend = Math.min(28, (x2 - x1) / 2);
  return `M ${x1} ${a.y} C ${x1 + bend} ${a.y}, ${x2 - bend} ${b.y}, ${x2} ${b.y}`;
}

function edgePath(e, pos) {
  const a = pos[e.from], b = pos[e.to];
  if (!a || !b) return null;
  const da = dimsOf(e.from), db = dimsOf(e.to);
  if (show.layout === "timeline" && e.kind === "tree"
      && bySlug[e.from].graph === "record" && bySlug[e.to].graph === "record")
    return timelineEdgePath(a, b, da, db);
  if (show.style === "circles" && styleFor(bySlug[e.from]) === "circle") {
    const dx = b.x - a.x, dy = b.y - a.y;  // straight, trimmed to the perimeters
    const d = Math.sqrt(dx * dx + dy * dy) || 1;
    const ux = dx / d, uy = dy / d;
    return `M ${a.x + ux * R} ${a.y + uy * R} L ${b.x - ux * R} ${b.y - uy * R}`;
  }
  if (show.layout === "force" || show.layout === "board") {
    const p1 = trimToRect(a, b, da), p2 = trimToRect(b, a, db);
    return `M ${p1.x} ${p1.y} L ${p2.x} ${p2.y}`;
  }
  if (e.kind === "tree" && !e.side) {
    const y1 = a.y + da.h / 2, y2 = b.y - db.h / 2, ym = (y1 + y2) / 2;
    return `M ${a.x} ${y1} C ${a.x} ${ym}, ${b.x} ${ym}, ${b.x} ${y2}`;
  }
  if (e.kind === "tree") {
    const dir = e.side === "left" ? -1 : 1;
    const x = a.x + dir * da.w / 2, x2 = b.x + dir * db.w / 2;
    const off = 26 + 0.055 * Math.abs(b.y - a.y);
    return `M ${x} ${a.y} C ${x + dir * off} ${a.y}, ${x2 + dir * off} ${b.y}, ${x2} ${b.y}`;
  }
  const fromState = bySlug[e.from].graph === "state";
  const x1 = a.x + (fromState ? -da.w / 2 : da.w / 2);
  const x2 = b.x + (bySlug[e.to].graph === "state" ? -db.w / 2 : db.w / 2);
  const cx = (x1 + x2) / 2;
  return `M ${x1} ${a.y} C ${cx} ${a.y}, ${cx} ${b.y}, ${x2} ${b.y}`;
}

const SPINE_SPREAD = 96;   // width of the staggered spine, in world px

// Seat each claim on the spine, ordered by its position in the state column, so
// neighbouring claims get neighbouring seats and their ribbons do not cross.
let _spineRank = null;
function stateSpineRank() {
  if (_spineRank) return _spineRank;
  const order = DATA.state.nodes.slice().sort((a, b) => {
    const pa = posFor()[a.slug], pb = posFor()[b.slug];
    return (pa ? pa.y : 0) - (pb ? pb.y : 0);
  });
  _spineRank = { count: order.length };
  order.forEach((n, i) => _spineRank[n.slug] = i);
  return _spineRank;
}

// In `all` mode every cross-link belonging to one state node is routed through a
// shared waist on a vertical spine at mid-x, so 176 separate lines read as a
// dozen ribbons — you can see *which claim* a bundle serves, which is the thing
// the hairball hid. Straight-through beziers are kept for the focused view,
// where there are only a few lines and precision beats grouping.
function bundledCrossPath(e, pos) {
  const a = pos[e.from], b = pos[e.to];
  if (!a || !b) return null;
  const da = dimsOf(e.from), db = dimsOf(e.to);
  const fromState = bySlug[e.from].graph === "state";
  const x1 = a.x + (fromState ? -da.w / 2 : da.w / 2);
  const x2 = b.x + (bySlug[e.to].graph === "state" ? -db.w / 2 : db.w / 2);
  const st = pos[e.state];
  if (!st) return edgePath(e, pos);
  // Stagger each claim's waist along the spine, or every bundle would pinch at
  // the same x and the ribbons would be indistinguishable exactly where they
  // are densest.
  const rank = stateSpineRank();
  const seat = rank[e.state] || 0, seats = Math.max(1, rank.count - 1);
  const wx = (x1 + x2) / 2 + (seat / seats - 0.5) * SPINE_SPREAD;
  const wy = st.y;                                 // the waist, shared per claim
  return `M ${x1} ${a.y} C ${(x1 + wx) / 2} ${a.y}, ${wx} ${(a.y + wy) / 2}, ${wx} ${wy}` +
         ` C ${wx} ${(wy + b.y) / 2}, ${(wx + x2) / 2} ${b.y}, ${x2} ${b.y}`;
}

function crossPath(e, pos) {
  return show.links === "all" ? bundledCrossPath(e, pos) : edgePath(e, pos);
}

// ------------------------------------------------------------------ render
function markerDefs() {
  const defs = el("defs");
  const kinds = { tree: T().axis, prov: T().prov, imp: T().impact };
  for (const id in kinds) {
    const m = el("marker", { id: "arrow-" + id, viewBox: "0 0 10 10",
      refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse" });
    m.appendChild(el("path", { d: "M 0 1 L 9 5 L 0 9 z", fill: kinds[id] }));
    defs.appendChild(m);
  }
  return defs;
}

function accentFor(entry) {
  const { graph, node } = entry;
  if (graph === "state")
    return node.is_root ? T().ink2 : (T().status[node.status] || T().muted);
  if (node.is_hwm) return T().hwm;
  if (node.unreconciled) return T().unrec;
  return node.is_root ? T().ink2 : T().axis;
}

function nodeXf(p, entry) {
  const shape = styleFor(entry);
  if (shape === "circle" || shape === "puck") return `translate(${p.x},${p.y})`;
  const d = dimsFor(entry);
  return `translate(${p.x - d.w / 2},${p.y - d.h / 2})`;
}

function drawNode(entry, pos) {
  const { graph, node } = entry;
  const p = pos[node.slug];
  const g = el("g", { class: "node", "data-slug": node.slug, cursor: "pointer",
                      transform: nodeXf(p, entry) });
  const frontier = graph === "state" && node.frontier;
  // card rect must stay firstChild (updateDim restyles it)
  g.appendChild(el("rect", { x: .5, y: .5, width: NW - 1, height: NH - 1, rx: 9,
    fill: T().surface, stroke: frontier ? accentFor(entry) : T().border,
    "stroke-width": frontier ? 1.4 : 1 }));
  g.appendChild(el("rect", { x: 3, y: 7, width: 4, height: NH - 14, rx: 2,
    fill: accentFor(entry) }));
  g.appendChild(el("text", { x: 16, y: 21, "font-family": FONT, "font-size": 12.5,
    "font-weight": node.is_root ? 700 : 600, fill: T().ink }, trunc(node.title, 32)));
  g.appendChild(el("text", { class: "detail", x: 16, y: 36.5, "font-family": MONO,
    "font-size": 10.5, fill: T().muted }, node.slug));
  let x = 16;
  const meta = (text, color, bold) => {
    const t = el("text", { class: "detail", x, y: 52, "font-family": FONT,
      "font-size": 10.5, fill: color, "font-weight": bold ? 650 : 400 }, text);
    g.appendChild(t);
    x += text.length * 6.3 + 13;
  };
  if (graph === "state") {
    if (node.is_root) meta("state root", T().ink2, true);
    else {
      g.appendChild(el("circle", { cx: x + 3.5, cy: 48.5, r: 3.5,
        fill: T().status[node.status] || T().muted }));
      x += 12;
      meta(node.status || "?", T().ink2);
      if (frontier) meta("frontier", T().ink2, true);
    }
  } else {
    meta((node.created_at || "").slice(0, 10), T().muted);
    if (node.is_root) meta("record root", T().ink2, true);
    if (node.is_hwm) meta("HWM", T().hwm, true);
    if (node.unreconciled) meta("unreconciled", T().unrec, true);
    if (node.impact_none != null) meta("no impact", T().muted);
    else if (node.impacts.length)
      meta(node.impacts.length + " impact" + (node.impacts.length > 1 ? "s" : ""), T().ink2);
  }
  const tip = el("title");
  tip.textContent = node.title + " (" + node.slug + ")";
  g.appendChild(tip);
  return g;
}

// Circle style: nodes as plain circles (record or state). The circle must stay
// firstChild (updateDim restyles it); <title> hover tooltip appended last.
function drawCircleNode(entry, pos) {
  const { node } = entry;
  const p = pos[node.slug];
  const g = el("g", { class: "node", "data-slug": node.slug, cursor: "pointer",
                      transform: nodeXf(p, entry) });
  const heavy = node.is_root || node.is_hwm || node.unreconciled || node.frontier;
  g.appendChild(el("circle", { r: R, fill: T().surface, stroke: accentFor(entry),
    "stroke-width": heavy ? 2.2 : 1.4 }));
  // The circle style used to be unlabelled by design, which made the Clusters
  // view unreadable: you could see the grouping and not what was grouped. The
  // label is drawn always and shown by zoom (applyTf), so panning stays cheap.
  g.appendChild(el("text", { class: "nodelabel", x: 0, y: R + 13,
    "font-family": FONT, "font-size": 10.5, "text-anchor": "middle",
    fill: T().ink2, "pointer-events": "none" }, trunc(node.title, 20)));
  const tip = el("title");
  tip.textContent = node.title + " (" + node.slug + ")";
  g.appendChild(tip);
  return g;
}

// Timeline chip: one line of title at full reading size, plus a status pip.
// Everything else about the node is one click away, which is the trade that
// keeps 39 of these legible side by side.
function drawChipNode(entry, pos) {
  const { node } = entry;
  const p = pos[node.slug];
  const accent = accentFor(entry);
  const marked = node.is_root || node.is_hwm || node.unreconciled;
  const g = el("g", { class: "node", "data-slug": node.slug, cursor: "pointer",
                      transform: nodeXf(p, entry) });
  g.appendChild(el("rect", { x: .5, y: .5, width: CW - 1, height: CH - 1, rx: 6,
    fill: T().surface, stroke: marked ? accent : T().border,
    "stroke-width": marked ? 1.4 : 1 }));
  g.appendChild(el("rect", { x: 0, y: 0, width: 3.5, height: CH, rx: 1.75,
    fill: accent }));
  g.appendChild(el("text", { x: 10, y: CH / 2 + 4, "font-family": FONT,
    "font-size": 11.5, "font-weight": node.is_root || node.is_hwm ? 650 : 500,
    fill: T().ink }, trunc(node.title, 24)));
  const tip = el("title");
  tip.textContent = (node.created_at || "").slice(0, 10) + " · " + node.title +
                    " (" + node.slug + ")";
  g.appendChild(tip);
  return g;
}

// Frontier board card: title, slug, status dot, how much record work stands
// behind the claim, and when the newest of it landed.
function drawBoardCard(entry, pos) {
  const { node } = entry;
  const p = pos[node.slug];
  const accent = accentFor(entry);
  const g = el("g", { class: "node", "data-slug": node.slug, cursor: "pointer",
                      transform: nodeXf(p, entry) });
  g.appendChild(el("rect", { x: .5, y: .5, width: BW - 1, height: BH - 1, rx: 10,
    fill: T().surface, stroke: node.frontier ? accent : T().border,
    "stroke-width": node.frontier ? 1.6 : 1 }));
  g.appendChild(el("rect", { x: 0, y: 0, width: 4, height: BH, rx: 2, fill: accent }));
  g.appendChild(el("text", { x: 15, y: 22, "font-family": FONT, "font-size": 13,
    "font-weight": node.is_root ? 700 : 620, fill: T().ink },
    trunc(node.title, 26)));
  g.appendChild(el("text", { class: "detail", x: 15, y: 39, "font-family": MONO,
    "font-size": 10.5, fill: T().muted }, node.slug));
  if (node.is_root) {
    g.appendChild(el("text", { x: 15, y: 60, "font-family": FONT, "font-size": 11,
      fill: T().ink2, "font-weight": 650 }, "state root"));
  } else {
    g.appendChild(el("circle", { cx: 18.5, cy: 56.5, r: 3.5, fill: accent }));
    g.appendChild(el("text", { x: 27, y: 60, "font-family": FONT, "font-size": 11,
      fill: T().ink2 }, node.status || "?"));
    const facts = [];
    if (node.prov_count) facts.push(node.prov_count + " prov");
    if (node.last_record_at) facts.push((node.last_record_at || "").slice(0, 10));
    if (facts.length)
      g.appendChild(el("text", { x: BW - 13, y: 60, "font-family": FONT,
        "font-size": 10.5, fill: T().muted, "text-anchor": "end" },
        facts.join(" · ")));
  }
  const tip = el("title");
  tip.textContent = node.title + " (" + node.slug + ")";
  g.appendChild(tip);
  return g;
}

// A collapsed hyperedge: one body carrying the claim's colour and its size.
// Clicking it opens the claim, where the button to expand it again lives.
function drawPuck(entry, pos) {
  const h = hyperedges().index[entry.state];
  const color = T().cat[(h ? h.ci : 0) % T().cat.length];
  const p = pos[entry.node.slug];
  const g = el("g", { class: "node", "data-slug": entry.node.slug,
                      cursor: "pointer", transform: nodeXf(p, entry) });
  g.appendChild(el("circle", { r: PUCK_R, fill: color, "fill-opacity": 0.18,
    stroke: color, "stroke-width": 2 }));
  g.appendChild(el("text", { x: 0, y: 4, "font-family": FONT, "font-size": 14,
    "font-weight": 700, "text-anchor": "middle", fill: color,
    "pointer-events": "none" }, String(entry.node.members)));
  g.appendChild(el("text", { class: "nodelabel", x: 0, y: PUCK_R + 14,
    "font-family": MONO, "font-size": 10.5, "text-anchor": "middle",
    fill: color, "pointer-events": "none" }, entry.state));
  const tip = el("title");
  tip.textContent = entry.node.title + " — " + entry.node.members +
                    " record nodes, collapsed";
  g.appendChild(tip);
  return g;
}

function drawAnyNode(entry, pos) {
  switch (styleFor(entry)) {
    case "puck":   return drawPuck(entry, pos);
    case "chip":   return drawChipNode(entry, pos);
    case "board":  return drawBoardCard(entry, pos);
    case "circle": return drawCircleNode(entry, pos);
    default:       return drawNode(entry, pos);
  }
}

// --------------------------------------------------------------- furniture
// Layout-specific scenery: the lane ruler and date gutter of the timeline, the
// column headers of the board. Drawn behind everything and never interactive.
function drawTimelineFurniture(pos) {
  const f = timelineFurniture(pos);
  if (!f) return null;
  const layer = el("g", { id: "furniture", "pointer-events": "none" });
  for (let i = 0; i < f.laneCount; i++) {  // one rule per lane, faint
    const y = i * LANE_H;
    layer.appendChild(el("line", { x1: f.x0, y1: y, x2: f.x1, y2: y,
      stroke: T().grid, "stroke-width": 1 }));
    layer.appendChild(el("text", { x: f.x0 - 10, y: y + 4, "font-family": MONO,
      "font-size": 10, fill: T().muted, "text-anchor": "end" }, "lane " + i));
  }
  const gutter = f.top - 6;
  f.ticks.forEach(t => {
    layer.appendChild(el("line", { x1: t.x, y1: gutter + 4, x2: t.x, y2: f.bottom,
      stroke: T().grid, "stroke-width": 1, "stroke-dasharray": "2 5" }));
    layer.appendChild(el("text", { x: t.x, y: gutter, "font-family": MONO,
      "font-size": 10, fill: T().muted, "text-anchor": "middle" }, t.label));
  });
  if (f.hwmX != null) {  // everything right of the rule is not yet reconciled
    layer.appendChild(el("rect", { x: f.hwmX, y: f.top - 2,
      width: Math.max(0, f.x1 - f.hwmX), height: f.bottom - f.top + 2,
      fill: T().unrec, opacity: 0.07 }));
    layer.appendChild(el("line", { x1: f.hwmX, y1: f.top - 2, x2: f.hwmX,
      y2: f.bottom, stroke: T().hwm, "stroke-width": 1.4, opacity: 0.7 }));
    layer.appendChild(el("text", { x: f.hwmX + 6, y: f.bottom + 12,
      "font-family": FONT, "font-size": 10.5, fill: T().hwm },
      "high-water mark →  unreconciled"));
  }
  return layer;
}

function drawBoardFurniture() {
  const f = boardFurniture();
  if (!f) return null;
  const layer = el("g", { id: "furniture", "pointer-events": "none" });
  const top = f.headerY - 18;
  f.columns.forEach(c => {
    layer.appendChild(el("rect", { x: c.x - 10, y: top,
      width: c.w + 20, height: f.height - top + 12, rx: 12,
      fill: T().grid, opacity: 0.35 }));
    const dot = el("circle", { r: 4, fill: T().status[c.status] || T().muted });
    const text = el("text", { "font-family": FONT, "font-size": 11.5,
      "font-weight": 700, fill: T().ink2, "letter-spacing": "0.06em" },
      c.status.toUpperCase() + "  " + c.count);
    if (c.rail) {  // collapsed: the header turns and runs down the rail
      dot.setAttribute("cx", c.x + c.w / 2);
      dot.setAttribute("cy", f.headerY - 4);
      text.setAttribute("x", c.x + c.w / 2 + 4);
      text.setAttribute("y", f.headerY + 12);
      text.setAttribute("text-anchor", "start");
      text.setAttribute("transform",
        `rotate(90 ${c.x + c.w / 2 + 4} ${f.headerY + 12})`);
    } else {
      dot.setAttribute("cx", c.x + 5);
      dot.setAttribute("cy", f.headerY - 4);
      text.setAttribute("x", c.x + 15);
      text.setAttribute("y", f.headerY);
    }
    layer.appendChild(dot);
    layer.appendChild(text);
  });
  return layer;
}

let blobEls = {};
function drawBlobs(pos) {
  const layer = el("g", { id: "blobs" });
  blobEls = {};
  const lps = blobLabelPositions(pos);
  const hs = hyperedges().list.slice()
    .sort((a, b) => b.members.length - a.members.length);  // big first, small on top
  hs.forEach(h => {
    // A collapsed claim is represented by its puck; drawing its blob as well —
    // around whatever members another claim still keeps on screen — would be two
    // contradictory pictures of the same thing.
    if (collapsed.has(h.state)) return;
    const d = blobPathFor(h, pos);
    if (!d) return;
    const color = T().cat[h.ci % T().cat.length];
    const path = el("path", { d, fill: color,
      "fill-opacity": theme === "dark" ? 0.18 : 0.14,
      stroke: color, "stroke-opacity": 0.45, "stroke-width": 1.2,
      "data-state": h.state, "pointer-events": "none" });
    const tip = el("title");
    tip.textContent = bySlug[h.state].node.title + " (" + h.state + ")";
    path.appendChild(tip);
    const lp = lps[h.state];
    const label = el("text", { x: lp.x, y: lp.y, class: "bloblabel",
      "data-slug": h.state, cursor: "pointer", "font-family": MONO,
      "font-size": 10.5, "text-anchor": "middle", fill: color }, h.state);
    layer.appendChild(path);
    layer.appendChild(label);
    blobEls[h.state] = { path, label };
  });
  return layer;
}

function updateBlobs(slug) {
  const pos = posFor(), H = hyperedges();
  (H.memberOf[slug] || []).forEach(st => {
    const be = blobEls[st];
    if (be) be.path.setAttribute("d", blobPathFor(H.index[st], pos));
  });
  const lps = blobLabelPositions(pos);  // placement involves every label
  for (const st in blobEls) {
    blobEls[st].label.setAttribute("x", lps[st].x);
    blobEls[st].label.setAttribute("y", lps[st].y);
  }
}

// Redraw only the blob layer — after a drag ends (the field replaces the hull
// used while dragging) or after zooming across the field threshold.
function redrawBlobs() {
  const world = document.getElementById("world");
  const old = document.getElementById("blobs");
  if (!world || !old) return;
  const fresh = drawBlobs(posFor());
  world.replaceChild(fresh, old);
  updateDim();
}

function renderAll() {
  const pos = posFor();
  svg.textContent = "";
  svg.appendChild(markerDefs());
  const world = el("g", { id: "world" });
  svg.appendChild(world);
  blobEls = {};
  const furniture = show.layout === "timeline" ? drawTimelineFurniture(pos)
                  : show.layout === "board" ? drawBoardFurniture() : null;
  if (furniture) world.appendChild(furniture);                    // behind everything
  if (show.blobs && recVis()) world.appendChild(drawBlobs(pos));
  const edgeLayer = el("g", { id: "edges" });
  const nodeLayer = el("g", { id: "nodes" });
  world.appendChild(edgeLayer);
  world.appendChild(el("g", { id: "crosslinks" }));
  world.appendChild(nodeLayer);

  if (show.layout === "layered" && show.graphs === "both") {
    const head = (text, x, anchor) => nodeLayer.appendChild(el("text", { x, y: -64,
      "font-family": FONT, "font-size": 12, "font-weight": 700, fill: T().muted,
      "letter-spacing": "0.08em", "text-anchor": anchor }, text));
    head("RECORD — " + DATA.record.nodes.length + " nodes (append-only log)", 0, "middle");
    head("STATE — " + DATA.state.nodes.length + " nodes (distilled now)",
         comboStateX(), "middle");
  }

  edges = edgesFor();
  edgeEls = [];
  const quiet = show.style === "circles";  // tree edges stay understated there
  edges.forEach(e => {
    const d = edgePath(e, pos);
    if (!d) { edgeEls.push(null); return; }
    const style = e.kind === "tree"
      ? (quiet ? { stroke: T().axis, marker: null, dash: null, op: 0.55, w: 1 }
               : { stroke: T().axis, marker: "arrow-tree", dash: null, op: 0.9, w: 1.4 })
      : e.kind === "impact"
        ? { stroke: T().impact, marker: "arrow-imp", dash: "6 4", op: 0.8, w: 1.6 }
        : { stroke: T().prov, marker: "arrow-prov", dash: null, op: 0.65, w: 1.6 };
    const path = el("path", { d, fill: "none", stroke: style.stroke,
      "stroke-width": style.w, opacity: style.op });
    if (style.marker) path.setAttribute("marker-end", `url(#${style.marker})`);
    path.dataset.op = style.op;
    if (style.dash) path.setAttribute("stroke-dasharray", style.dash);
    if (e.label) {
      const tip = el("title");
      tip.textContent = e.kind + ": " + e.label;
      path.appendChild(tip);
    }
    edgeLayer.appendChild(path);
    edgeEls.push(path);
  });

  nodeEls = {};
  const draw = g => DATA[g].nodes.forEach(n => {
    if (!pos[n.slug]) return;
    const gEl = drawAnyNode(bySlug[n.slug], pos);
    nodeLayer.appendChild(gEl);
    nodeEls[n.slug] = gEl;
  });
  if (recVis()) draw("record");
  if (stVis()) draw("state");
  collapsed.forEach(state => {           // one puck per collapsed hyperedge
    const slug = puckKey(state);
    if (!pos[slug] || !bySlug[slug]) return;
    const gEl = drawAnyNode(bySlug[slug], pos);
    nodeLayer.appendChild(gEl);
    nodeEls[slug] = gEl;
  });

  renderCrossLinks();
  applyTf();
  updateDim();
}

// The cross-link layer is rebuilt rather than dimmed, because in `focus` mode
// the answer is usually "draw nothing at all" and the cheapest way to draw
// nothing is to build nothing.
let crossEdges = [], crossEls = [];
function renderCrossLinks() {
  const layer = document.getElementById("crosslinks");
  if (!layer) return;
  layer.textContent = "";
  _spineRank = null;          // positions may have changed; reseat the spine
  const pos = posFor();
  crossEdges = crossLinksFor();
  crossEls = [];
  const bundled = show.links === "all";
  crossEdges.forEach(e => {
    const d = crossPath(e, pos);
    if (!d) { crossEls.push(null); return; }
    const style = e.kind === "impact"
      ? { stroke: T().impact, marker: "arrow-imp", dash: "6 4", op: bundled ? 0.5 : 0.85 }
      : { stroke: T().prov, marker: "arrow-prov", dash: null, op: bundled ? 0.4 : 0.75 };
    const path = el("path", { d, fill: "none", stroke: style.stroke,
      "stroke-width": bundled ? 1.1 : 1.8, opacity: style.op });
    // Bundled ribbons carry no arrowheads: 176 of them turn into visual noise,
    // and the direction is already given by which column each end sits in.
    if (!bundled) path.setAttribute("marker-end", `url(#${style.marker})`);
    if (style.dash) path.setAttribute("stroke-dasharray", style.dash);
    path.dataset.op = style.op;
    if (e.label) {
      const tip = el("title");
      tip.textContent = e.kind + ": " + e.label;
      path.appendChild(tip);
    }
    layer.appendChild(path);
    crossEls.push(path);
  });
}

// Below this zoom a 10.5px label is under 7px on screen — noise, not text.
const LABEL_MIN_ZOOM = 0.62;

// Level of detail. Text that cannot be read costs layout and paint time for
// nothing, so it is switched off by zoom rather than drawn small: secondary
// lines first, then all node text, leaving a coloured box that still reads as a
// shape at a glance.
function applyLod(k) {
  const set = (sel, on) =>
    svg.querySelectorAll(sel).forEach(e => e.style.display = on ? "" : "none");
  set("text.nodelabel", k >= LABEL_MIN_ZOOM);
  set("#nodes text.detail", k >= DETAIL_MIN_ZOOM);
  const nodes = document.getElementById("nodes");
  if (nodes) nodes.style.setProperty("--lod-text", k >= TEXT_MIN_ZOOM ? "1" : "0");
  set("#nodes text:not(.nodelabel):not(.detail)", k >= TEXT_MIN_ZOOM);
}

function applyTf() {
  const t = tfFor();
  const world = document.getElementById("world");
  if (world) world.setAttribute("transform", `translate(${t.x},${t.y}) scale(${t.k})`);
  applyLod(t.k);
}

// ------------------------------------------------------- dim / select / search
function neighborhood(slug) {
  const rel = new Set([slug]);
  edges.forEach(e => {
    if (e.from === slug) rel.add(e.to);
    if (e.to === slug) rel.add(e.from);
  });
  // Cross-graph neighbours come from the data, not from what is currently
  // drawn: in `focus` mode nothing is drawn until something is selected, and
  // the selection is what decides the neighbourhood in the first place.
  if (show.graphs === "both") DATA.links.forEach(l => {
    if (l.record === slug) rel.add(l.state);
    if (l.state === slug) rel.add(l.record);
  });
  if (show.blobs && recVis()) {  // union in hyperedge co-members / members
    const H = hyperedges();
    (H.memberOf[slug] || []).forEach(st =>
      H.index[st].members.forEach(m => rel.add(m)));
    if (H.index[slug]) H.index[slug].members.forEach(m => rel.add(m));
  }
  return rel;
}

function matches(node) {
  if (!query) return true;
  return (node.slug + " " + node.title + " " + node.content).toLowerCase().includes(query);
}

function updateDim() {
  const rel = selected ? neighborhood(selected) : null;
  const vis = {};
  for (const slug in nodeEls) {
    const entry = bySlug[slug];
    const m = matches(entry.node);
    const op = !m ? 0.12 : (rel && !rel.has(slug)) ? 0.3 : 1;
    vis[slug] = op === 1;
    nodeEls[slug].setAttribute("opacity", op);
    const box = nodeEls[slug].firstChild;  // the shape stays firstChild in every draw*
    const shape = styleFor(entry);
    const n = entry.node;
    if (shape === "puck") {
      box.setAttribute("stroke-width", slug === selected ? 3.2 : 2);
    } else if (shape === "circle") {
      const heavy = n.is_root || n.is_hwm || n.unreconciled || n.frontier;
      box.setAttribute("stroke", slug === selected ? T().ink : accentFor(entry));
      box.setAttribute("stroke-width", slug === selected ? 2.4 : heavy ? 2.2 : 1.4);
    } else {
      // Marked = something the reader should not miss: the frontier on a state
      // node, the root / high-water mark / unreconciled tail on a record node.
      const marked = shape === "chip"
        ? (n.is_root || n.is_hwm || n.unreconciled)
        : (entry.graph === "state" && n.frontier);
      const heavy = shape === "board" ? 1.6 : 1.4;
      box.setAttribute("stroke", slug === selected ? T().ink
        : marked ? accentFor(entry) : T().border);
      box.setAttribute("stroke-width", slug === selected ? heavy + 0.4
        : marked ? heavy : 1);
    }
  }
  for (const st in blobEls) {  // dim via a separate opacity attr; base attrs
    const h = hyperedges().index[st];  // stay untouched for the SVG export
    let on = true;
    if (selected) on = selected === st || h.members.includes(selected);
    else if (query) on = matches(bySlug[st].node) ||
      h.members.some(m => matches(bySlug[m].node));
    blobEls[st].path.setAttribute("opacity", on ? 1 : 0.12);
    blobEls[st].label.setAttribute("opacity", on ? 1 : 0.12);
  }
  const dimEdges = (list, els) => list.forEach((e, i) => {
    const pathEl = els[i];
    if (!pathEl) return;
    const on = vis[e.from] !== false && vis[e.to] !== false &&
      (!rel || e.from === selected || e.to === selected);
    pathEl.setAttribute("opacity", on ? pathEl.dataset.op : 0.08);
  });
  dimEdges(edges, edgeEls);
  dimEdges(crossEdges, crossEls);
}

// Hovering a node is enough to reveal its cross-graph links in `focus` mode —
// selecting is for reading the panel, hovering is for "what does this touch?".
let hovered = null;
function setHovered(slug) {
  if (hovered === slug) return;
  hovered = slug;
  if (show.links === "focus" && show.graphs === "both") {
    renderCrossLinks();
    updateDim();
  }
}

function select(slug) {
  selected = slug;
  renderCrossLinks();
  updateDim();
  renderPanel();
}
function deselect() { selected = null; renderCrossLinks(); updateDim(); renderPanel(); }

function jumpTo(slug) {
  const entry = bySlug[slug];
  if (!entry) return;
  const visible = entry.graph === "record" ? recVis() : stVis();
  if (!visible) {
    show.graphs = "both";
    syncControls();
    renderAll();
    fitDone[layoutKey()] = true;  // jumpTo centers on the target itself
  }
  select(slug);
  const p = posFor()[slug];
  if (!p) return;
  const t = tfFor(), r = svg.getBoundingClientRect();
  t.x = r.width / 2 - p.x * t.k;
  t.y = r.height / 2 - p.y * t.k;
  applyTf();
}

