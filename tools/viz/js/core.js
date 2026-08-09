"use strict";
const DATA = __VIZ_DATA__;

const THEMES = {
  light: { surface:"#fcfcfb", page:"#f9f9f7", ink:"#0b0b0b", ink2:"#52514e",
    muted:"#898781", grid:"#e1e0d9", axis:"#c3c2b7", border:"rgba(11,11,11,0.10)",
    status:{ working:"#0ca30c", open:"#2a78d6", broken:"#d03b3b",
             blocked:"#fab219", superseded:"#898781" },
    prov:"#2a78d6", impact:"#eb6834", hwm:"#4a3aa7", unrec:"#fab219",
    cat:["#2a78d6","#eb6834","#0ca30c","#4a3aa7","#c22f7a","#0b8f8f",
         "#a8790a","#5f7a2a"] },
  dark: { surface:"#1a1a19", page:"#0d0d0d", ink:"#ffffff", ink2:"#c3c2b7",
    muted:"#898781", grid:"#2c2c2a", axis:"#383835", border:"rgba(255,255,255,0.10)",
    status:{ working:"#0ca30c", open:"#3987e5", broken:"#d03b3b",
             blocked:"#fab219", superseded:"#898781" },
    prov:"#3987e5", impact:"#d95926", hwm:"#9085e9", unrec:"#fab219",
    cat:["#3987e5","#f0784a","#33bb33","#9085e9","#e05a9b","#33b8b8",
         "#d9a521","#8fae4a"] },
};
const SVGNS = "http://www.w3.org/2000/svg";
const NW = 236, NH = 62;
const R = 16, BPAD = 18;  // circle style: circle radius, blob hull padding
// Timeline chips: deliberately small, because 39 of them sit side by side along
// one time axis. The full title is one click away in the panel.
const CW = 158, CH = 26, LANE_H = 42, RANK_STEP = CW + 16;
const BW = 232, BH = 78, BCOL = BW + 26, BROW = BH + 12;  // frontier board cards
// Nothing may fit below this. Shrinking past it trades "you can see everything"
// for "you can read nothing" — the view scrolls instead.
const MIN_FIT = 0.45, MAX_FIT = 1.25;
const FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif';
const MONO = "ui-monospace, SFMono-Regular, Menlo, monospace";
const SLUG_JS = /\b[a-z][a-z0-9]*-[a-z][a-z0-9]*-[0-9]{4}\b/g;

const bySlug = {};
DATA.record.nodes.forEach(n => bySlug[n.slug] = { graph: "record", node: n });
DATA.state.nodes.forEach(n => bySlug[n.slug] = { graph: "state", node: n });

// Display state: one unified view driven by toggles. The four views below are
// named after the job they do; any custom mix of toggles is equally valid.
const show = {
  graphs: "record",   // "record" | "state" | "both"
  style:  "circles",  // "cards" | "circles"
  layout: "force",    // "timeline" | "board" | "layered" | "force"
  xaxis:  "rank",     // timeline only: "rank" (even) | "time" (real dates)
  board:  "status",   // board only: "status" columns | "tree" architecture
  tree:   true,       // intra-graph parent edges
  impact: false,      // cross-graph impact links (needs graphs === "both")
  prov:   false,      // cross-graph provenance links (ditto)
  blobs:  true,       // hyperedge blobs (needs the record graph visible)
};
const recVis = () => show.graphs !== "state";
const stVis  = () => show.graphs !== "record";
// Two layouts are about one graph each and say so: picking Lanes means you want
// the record graph, picking Board means you want the state graph.
const LAYOUT_GRAPH = { timeline: "record", board: "state" };
// Which segmented controls apply to the current layout; the rest stay hidden
// rather than dimmed, so the panel only ever offers real choices.
const SEG_FOR_LAYOUT = { xaxis: ["timeline"], board: ["board"] };
// Pan/zoom + node positions are cached per layout signature; edge/blob toggles
// deliberately excluded so flipping a checkbox never resets pan or drag state.
const layoutKey = () => [show.layout, show.graphs, show.style,
                         show.xaxis, show.board].join(":");

// Four views, each named after its job. Timeline = what happened, in order.
// Frontier = what is true now, and what is open. Provenance = which record work
// each state claim rests on. Clusters = which work belongs to the same claim.
const PRESETS = {
  timeline:   { graphs:"record", style:"cards",   layout:"timeline",
                xaxis:"rank", board:"status",
                tree:true, impact:false, prov:false, blobs:false },
  frontier:   { graphs:"state",  style:"cards",   layout:"board",
                xaxis:"rank", board:"status",
                tree:false, impact:false, prov:false, blobs:false },
  provenance: { graphs:"both",   style:"cards",   layout:"layered",
                xaxis:"rank", board:"status",
                tree:true, impact:true,  prov:true,  blobs:false },
  clusters:   { graphs:"record", style:"circles", layout:"force",
                xaxis:"rank", board:"status",
                tree:true, impact:false, prov:false, blobs:true },
};
// Pre-rename deep links keep working: #record #state #combo #combination #hyper.
const VIEW_ALIASES = { record:"timeline", state:"frontier", combo:"provenance",
                       combination:"provenance", hyper:"clusters" };
// Node shape follows the layout, not only the Nodes toggle: the timeline draws
// compact chips and the board draws status cards, because those two layouts exist
// precisely to show what a generic card cannot.
function styleFor(entry) {
  if (show.layout === "timeline" && entry.graph === "record") return "chip";
  if (show.layout === "board" && entry.graph === "state") return "board";
  return show.style === "circles" ? "circle" : "card";
}
function dimsFor(entry) {
  switch (styleFor(entry)) {
    case "chip":   return { w: CW, h: CH };
    case "board":  return { w: BW, h: BH };
    case "circle": return { w: 2 * R, h: 2 * R };
    default:       return { w: NW, h: NH };
  }
}
function dimsOf(slug) { return dimsFor(bySlug[slug]); }

function activePreset() {
  for (const name in PRESETS) {
    const p = PRESETS[name];
    if (Object.keys(show).every(k => show[k] === p[k])) return name;
  }
  return null;
}

let theme = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
let selected = null, query = "";
const tf = {}, positions = {}, fitDone = {};
function posFor() {
  const k = layoutKey();
  if (!positions[k]) positions[k] = computeLayout();
  return positions[k];
}
function tfFor() {
  const k = layoutKey();
  return tf[k] || (tf[k] = { x: 0, y: 0, k: 1 });
}
let nodeEls = {}, edgeEls = [], edges = [];

const svg = document.getElementById("svg");
const panel = document.getElementById("panel");

function el(name, attrs, text) {
  const e = document.createElementNS(SVGNS, name);
  for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
  if (text != null) e.textContent = text;
  return e;
}
function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function trunc(s, n) { return s.length > n ? s.slice(0, n - 1) + "…" : s; }
function T() { return THEMES[theme]; }

// ------------------------------------------------------------------ layout
// Hyperedges: one per state node targeted by >=1 impact link, in DATA.state
// order (stable color assignment). memberOf maps record slug -> [state slug].
let _hyper = null;
function hyperedges() {
  if (_hyper) return _hyper;
  const byState = {};
  DATA.links.forEach(l => {
    if (l.kind === "impact")
      (byState[l.state] = byState[l.state] || new Set()).add(l.record);
  });
  const list = [], memberOf = {}, index = {};
  DATA.state.nodes.forEach(n => {
    const set = byState[n.slug];
    if (!set) return;
    const members = DATA.record.nodes.filter(r => set.has(r.slug)).map(r => r.slug);
    if (!members.length) return;
    members.forEach(m => (memberOf[m] = memberOf[m] || []).push(n.slug));
    const h = { state: n.slug, members, ci: list.length };
    list.push(h);
    index[n.slug] = h;
  });
  _hyper = { list, memberOf, index };
  return _hyper;
}

// FNV-1a hash of a slug -> [0,1). Deterministic jitter source so the force
// layout is identical on every load (no randomness anywhere in this page).
function hashSlug(s) {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h / 4294967296;
}

