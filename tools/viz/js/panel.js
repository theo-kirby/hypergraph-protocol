// ------------------------------------------------------------------- panel
function slugLink(slug) {
  return bySlug[slug]
    ? `<a class="slug" data-slug="${slug}">${slug}</a>`
    : `<span class="slugchip">${slug}</span>`;
}

function mdlite(content) {
  const inline = s => esc(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(SLUG_JS, m => bySlug[m] ? slugLink(m) : m);
  const out = [];
  let list = null, para = [];
  const flushPara = () => {
    if (para.length) { out.push("<p>" + inline(para.join(" ")) + "</p>"); para = []; }
  };
  const flushList = () => {
    if (list) { out.push("<ul>" + list.join("") + "</ul>"); list = null; }
  };
  content.split("\n").forEach(line => {
    const t2 = line.trim();
    if (t2.startsWith("## ")) { flushPara(); flushList();
      out.push("<h4>" + inline(t2.slice(3)) + "</h4>"); }
    else if (t2.startsWith("- ")) { flushPara();
      (list = list || []).push("<li>" + inline(t2.slice(2)) + "</li>"); }
    else if (!t2) { flushPara(); flushList(); }
    else { flushList(); para.push(t2); }
  });
  flushPara(); flushList();
  return out.join("");
}

function chip(label, color) {
  const dot = color ? `<span class="dot" style="background:${color}"></span>` : "";
  return `<span class="chip">${dot}${esc(label)}</span>`;
}

function linkList(items) {
  if (!items.length) return '<p class="meta">none</p>';
  return '<ul class="links">' + items.map(i =>
    `<li>${slugLink(i.slug)} <span class="note">${esc(i.note || "")}</span></li>`
  ).join("") + "</ul>";
}

// Paths, not links. There is nothing to link to from a page that gets emailed and
// committed — a `file://` that resolves on one machine and 404s on every other reads
// worse than the path itself, which is always readable and always copyable.
function pathList(paths) {
  return '<ul class="paths">' + paths.map(p =>
    `<li><code>${esc(p)}</code></li>`).join("") + "</ul>";
}

function renderPanel() {
  if (!selected || !bySlug[selected]) { panel.innerHTML = legendHTML(); bindPanel(); return; }
  const { graph, node } = bySlug[selected];
  let chips = "";
  if (graph === "state") {
    if (node.is_root) chips += chip("state root");
    else chips += chip(node.status || "?", T().status[node.status]);
    if (node.frontier) chips += chip("frontier");
  } else {
    if (node.is_root) chips += chip("record root");
    if (node.is_hwm) chips += chip("high-water mark", T().hwm);
    if (node.unreconciled) chips += chip("unreconciled", T().unrec);
    if (node.impact_none != null) chips += chip("impact: none");
  }
  // Tags last, and in their own colours: they are annotation beside the protocol
  // facts above, not another one of them.
  (node.tags || []).forEach(name => {
    const def = (DATA.tag_defs || []).find(d => d.name === name);
    chips += `<span class="chip" style="background:${esc((def && def.bg_color) || "")};` +
             `color:${esc((def && def.text_color) || "")}">${esc(name)}</span>`;
  });
  let html = `
    <div class="meta">${graph} graph · created ${esc((node.created_at || "").slice(0, 16).replace("T", " "))}</div>
    <h2>${esc(node.title)}</h2>
    <div class="slugchip">${esc(node.slug)}</div>
    <div class="chips">${chips}</div>`;
  if (graph === "record") {
    if (node.impact_none != null)
      html += `<h3>State impact</h3><p class="meta">none: ${esc(node.impact_none)}</p>`;
    else if (node.impacts.length)
      html += "<h3>Declares impact on</h3>" + linkList(node.impacts.map(i => ({
        slug: i.resolved || i.target,
        note: (i.new ? "NEW · " : "") + i.delta })));
    const citedBy = DATA.links.filter(l => l.record === node.slug && l.kind === "provenance");
    html += "<h3>Cited as provenance by</h3>" +
      linkList(citedBy.map(l => ({ slug: l.state, note: l.label })));
  } else if (!node.is_root) {
    // A claim with an impact set can be folded to one puck. At 500 nodes that is
    // the difference between reading the shape of the work and reading a wall.
    const h = hyperedges().index[node.slug];
    if (h) {
      const on = collapsed.has(node.slug);
      html += `<h3>Cluster</h3><p class="meta">${h.members.length} record node` +
        `${h.members.length > 1 ? "s" : ""} declare impact on this claim.</p>` +
        `<button class="act" data-collapse="${node.slug}">` +
        `${on ? "Expand" : "Collapse to one puck"}</button>`;
    }
    const prov = DATA.links.filter(l => l.state === node.slug && l.kind === "provenance");
    html += "<h3>Derived from (provenance)</h3>" +
      linkList(prov.map(l => ({ slug: l.record, note: l.label })));
    const impacts = DATA.links.filter(l => l.state === node.slug && l.kind === "impact");
    html += "<h3>Impact declarations targeting this</h3>" +
      linkList(impacts.map(l => ({ slug: l.record, note: l.label })));
  }
  // Guarded on non-empty, so an artifact-less graph's panel is byte-identical to
  // what it was before this section existed.
  if ((node.artifacts || []).length)
    html += "<h3>Evidence</h3>" + pathList(node.artifacts);
  html += `<h3>Content</h3><div class="content">${mdlite(node.content)}</div>`;
  panel.innerHTML = html;
  bindPanel();
}

function legendHTML() {
  const S = T().status;
  const frontier = DATA.state.nodes.filter(n => n.frontier).length;
  const unrec = DATA.record.nodes.filter(n => n.unreconciled).length;
  const swatch = (color, dashed) =>
    `<span class="legend-swatch" style="border-top-color:${color};border-top-style:${dashed ? "dashed" : "solid"}"></span>`;
  return `
    <h2>__TITLE__</h2>
    <div class="meta">Two-graph hypergraph — click any node for details.</div>
    <h3>Reconciliation</h3>
    <table class="stats">
      <tr><td>record nodes</td><td>${DATA.record.nodes.length}</td></tr>
      <tr><td>state nodes</td><td>${DATA.state.nodes.length}</td></tr>
      <tr><td>cross-graph links</td><td>${DATA.links.length}</td></tr>
      <tr><td>frontier</td><td>${frontier}</td></tr>
      <tr><td>unreconciled</td><td>${unrec}</td></tr>
      <tr><td>high-water mark</td><td>${(DATA.reconciliation.high_water_frontier || []).length
        ? DATA.reconciliation.high_water_frontier.map(slugLink).join(", ") : "—"}</td></tr>
      <tr><td>reconciled at</td><td>${esc((DATA.reconciliation.reconciled_at || "—").slice(0, 16).replace("T", " "))}</td></tr>
    </table>
    <h3>State status</h3>
    <div class="chips">
      ${chip("working", S.working)}${chip("open", S.open)}${chip("broken", S.broken)}
      ${chip("blocked", S.blocked)}${chip("superseded", S.superseded)}
    </div>
    <div class="meta" style="margin-top:6px">frontier = open ∪ broken ∪ blocked (colored border)</div>
    <h3>Record markers</h3>
    <div class="chips">${chip("high-water mark", T().hwm)}${chip("unreconciled", T().unrec)}</div>
    <h3>Edges</h3>
    <table class="stats">
      <tr><td>${swatch(T().axis)}</td><td>parent → child (within one graph)</td></tr>
      <tr><td>${swatch(T().prov)}</td><td>provenance: state node derives from record node</td></tr>
      <tr><td>${swatch(T().impact, true)}</td><td>declared State Impact: record → state target</td></tr>
    </table>
    <h3>Views</h3>
    <table class="stats">
      <tr><td><b>Timeline</b></td><td>what happened, in order — <code>git log</code>
        lanes with time along x. A rule marks the high-water mark; the tinted band
        past it is work not yet reconciled.</td></tr>
      <tr><td><b>Frontier</b></td><td>what is true now — a status board, broken and
        blocked and open first. An empty column keeps a labelled rail, because
        "nothing is broken" is an answer.</td></tr>
      <tr><td><b>Provenance</b></td><td>what each claim rests on — both graphs side
        by side. Cross-links start hidden; select or hover a node to see its own,
        or switch Links to <i>All</i> for one bundled ribbon per claim.</td></tr>
      <tr><td><b>Clusters</b></td><td>which work belongs to the same claim — each
        claim's record set as a blob, with a corridor holding far-apart members
        together and non-members pushing the outline away.</td></tr>
      <tr><td><b>Everything</b></td><td>the default: both graphs, blobs, and every
        cross-link at once. Busy on purpose — it shows what is there before it
        shows you a slice of it, and the four views above are one key away.</td></tr>
    </table>
    <h3>Marks worth knowing</h3>
    <table class="stats">
      <tr><td>lane rules</td><td>concurrent threads of work in the Timeline</td></tr>
      <tr><td>puck</td><td>a claim collapsed to one body; the number is how many
        record nodes it holds. Open the claim to expand it again.</td></tr>
      <tr><td>Window</td><td>keeps only the most recent N record nodes, so a long
        history shrinks the drawing instead of scrolling past it</td></tr>
    </table>
    <p class="hint"><b>Keys</b> — <code>1</code>–<code>5</code> pick a view ·
    <code>/</code> search · <code>f</code> fit · <code>Esc</code> deselect.
    Scroll to zoom · drag the background to pan · drag nodes to rearrange ·
    click a node for its full content · drag the divider to resize this panel.
    <b>Arrange</b> moves the whole drawing — spread, tighten, relax from where
    things are, shuffle to another seeded arrangement, or reset. <b>Blob tuning</b>
    edits the outline geometry live and copies it as a <code>viz:</code> block for
    <code>.hypergraph/config.yml</code>.
    No view shrinks below 0.45 — one that does not fit scrolls instead. The
    layout is deterministic: the same graph always draws the same way. Use the
    export menu for SVG or PDF.</p>`;
}

function bindPanel() {
  panel.querySelectorAll("a.slug").forEach(a =>
    a.addEventListener("click", () => jumpTo(a.dataset.slug)));
  panel.querySelectorAll("button[data-collapse]").forEach(b =>
    b.addEventListener("click", () => toggleCollapse(b.dataset.collapse)));
}

function toggleCollapse(state) {
  if (collapsed.has(state)) collapsed.delete(state); else collapsed.add(state);
  rerender();
  renderPanel();
}

