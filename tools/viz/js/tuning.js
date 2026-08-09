// ------------------------------------------------------------------ tuning
// Live controls for the blob geometry, in the shape excaligraph's playground
// uses: one row per knob — label, current value, a dot when you have moved it
// off the default, and a line saying what it does.
//
// Every knob is a field of BLOB, and every reach in blob.js reads BLOB at call
// time, so writing the field *is* the plumbing. Nothing here touches `show`:
// activePreset() compares every key of that object against each preset, so a
// key the presets do not carry would darken every chip forever.
//
// Precedence: the hard defaults in blob.js, then the `viz.blob` block of
// .hypergraph/config.yml (baked into the page as DATA.settings.blob), then
// whatever this browser last saved. Reset drops the saved values and returns to
// what the config says — which is the point of putting the block in the config:
// a tuning you like travels with the repo instead of with your laptop.

const TUNE_STORE = "hypergraph.viz.blob";

const SLIDERS = [
  { key: "padding", group: "Shape", min: 0, max: 60, step: 1,
    hint: "Stand-off from each node's outline. It also rounds the outer corners." },
  { key: "corridor", group: "Shape", min: 0, max: 40, step: 1,
    hint: "Half-width of the band along the spanning tree — what keeps far-apart " +
          "members one body instead of separate islands." },
  { key: "smoothing", group: "Shape", min: 0, max: 60, step: 1,
    hint: "How softly the parts merge. This is the fillet: 0 gives hard seams " +
          "where two members meet." },
  { key: "clearance", group: "Shape", min: 0, max: 40, step: 1,
    hint: "How far the outline stays off a node that is not a member." },
  { key: "resolution", group: "Tracing", min: 2, max: 20, step: 1,
    hint: "Grid step for tracing the outline — smaller follows the true shape " +
          "and costs more." },
  { key: "tolerance", group: "Tracing", min: 0.2, max: 6, step: 0.1,
    hint: "How far a point may be dropped from the traced line. Higher is " +
          "simpler and flatter." },
  { key: "maxPoints", group: "Tracing", min: 40, max: 400, step: 10,
    hint: "Cap on points per outline. Past it, tracing coarsens rather than " +
          "emit hundreds." },
  { key: "dragCoarsen", group: "Tracing", min: 1, max: 5, step: 0.5,
    hint: "How much coarser the grid goes while you drag a node. Raise it if a " +
          "big cluster feels heavy." },
  { key: "fillOpacity", group: "Style", min: 0, max: 60, step: 1,
    hint: "Fill strength, in percent. Dark mode adds 4 on top." },
  { key: "strokeWidth", group: "Style", min: 0, max: 5, step: 0.5,
    hint: "Outline weight. 0 leaves the fill alone." },
  { key: "labelSize", group: "Style", min: 7, max: 20, step: 0.5,
    hint: "Type size of the claim slug drawn on the blob." },
];

// What Reset returns to: the hard defaults, overlaid by the config block. Filled
// in by initTuning before anything has had a chance to move.
const TUNE_BASE = {};

function tuneClamp(spec, value) {
  const n = Number(value);
  if (!isFinite(n)) return null;
  return Math.min(spec.max, Math.max(spec.min, n));
}

// localStorage is unavailable in some file:// sandboxes, and a page that throws
// there would be worse than one that simply does not remember.
function storedTuning() {
  try {
    return JSON.parse(localStorage.getItem(TUNE_STORE) || "{}") || {};
  } catch (err) { return {}; }
}
function saveTuning() {
  const out = {};
  SLIDERS.forEach(s => { if (BLOB[s.key] !== TUNE_BASE[s.key]) out[s.key] = BLOB[s.key]; });
  try {
    if (Object.keys(out).length) localStorage.setItem(TUNE_STORE, JSON.stringify(out));
    else localStorage.removeItem(TUNE_STORE);
  } catch (err) { /* no store: the sliders still work for this session */ }
}

function tuneFormat(spec, value) {
  return spec.step < 1 ? value.toFixed(1) : String(value);
}

function buildSliders() {
  const box = document.getElementById("sliders");
  if (!box) return;
  box.textContent = "";
  let group = null;
  SLIDERS.forEach(spec => {
    if (spec.group !== group) {
      group = spec.group;
      const head = document.createElement("div");
      head.className = "tunegroup";
      head.textContent = group;
      box.appendChild(head);
    }
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML =
      `<div class="rowhead"><span class="name">${spec.key}</span>` +
      `<span class="value" data-for="${spec.key}"></span></div>` +
      `<input type="range" min="${spec.min}" max="${spec.max}" step="${spec.step}">` +
      `<div class="hint">${esc(spec.hint)}</div>`;
    const input = row.querySelector("input");
    input.value = BLOB[spec.key];
    input.addEventListener("input", () => {
      const v = tuneClamp(spec, input.value);
      if (v === null) return;
      BLOB[spec.key] = v;
      markSlider(spec, v);
      saveTuning();
      applyTuning();
    });
    box.appendChild(row);
    markSlider(spec, BLOB[spec.key]);
  });
}

function markSlider(spec, value) {
  const cell = document.querySelector(`#sliders .value[data-for="${spec.key}"]`);
  if (!cell) return;
  cell.textContent = tuneFormat(spec, value);
  cell.classList.toggle("changed", value !== TUNE_BASE[spec.key]);
}

// Geometry and style both live in BLOB, so one repaint covers either. The cache
// is keyed on positions, which have not moved, so it has to be dropped by hand.
function applyTuning() {
  if (!show.blobs || !recVis()) return;
  blobCache.clear();
  redrawBlobs();
}

function resetTuning() {
  SLIDERS.forEach(spec => { BLOB[spec.key] = TUNE_BASE[spec.key]; });
  try { localStorage.removeItem(TUNE_STORE); } catch (err) { /* nothing to drop */ }
  buildSliders();
  applyTuning();
}

// The whole block, not only what moved: a config you paste should say what the
// page will do, without the reader holding the defaults in their head.
function tuningYaml() {
  const lines = ["viz:", "  blob:"];
  SLIDERS.forEach(spec => lines.push(`    ${spec.key}: ${tuneFormat(spec, BLOB[spec.key])}`));
  return lines.join("\n") + "\n";
}

function copyTuning(btn) {
  const text = tuningYaml();
  const done = ok => {
    btn.textContent = ok ? "Copied" : "Copy failed";
    setTimeout(() => { btn.textContent = "Copy as YAML"; }, 1400);
  };
  // A file:// page may have no clipboard API at all; the textarea route is the
  // old one and still works there.
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => done(true), () => done(fallbackCopy(text)));
    return;
  }
  done(fallbackCopy(text));
}

function fallbackCopy(text) {
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try { ok = document.execCommand("copy"); } catch (err) { ok = false; }
  ta.remove();
  return ok;
}

function initTuning() {
  const cfg = (DATA.settings && DATA.settings.blob) || {};
  SLIDERS.forEach(spec => {
    const fromConfig = tuneClamp(spec, cfg[spec.key]);
    TUNE_BASE[spec.key] = fromConfig === null ? BLOB[spec.key] : fromConfig;
    BLOB[spec.key] = TUNE_BASE[spec.key];
  });
  const saved = storedTuning();
  SLIDERS.forEach(spec => {
    const v = tuneClamp(spec, saved[spec.key]);
    if (v !== null) BLOB[spec.key] = v;
  });
  buildSliders();
  document.getElementById("tuneReset").addEventListener("click", resetTuning);
  const copy = document.getElementById("tuneCopy");
  copy.addEventListener("click", () => copyTuning(copy));
}
