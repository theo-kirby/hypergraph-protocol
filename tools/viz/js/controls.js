// -------------------------------------------------------------- interaction
let drag = null;
svg.addEventListener("pointerdown", e => {
  const lbl = e.target.closest ? e.target.closest(".bloblabel") : null;
  const nodeG = e.target.closest ? e.target.closest(".node") : null;
  if (nodeG) {
    const slug = nodeG.dataset.slug;
    const p = posFor()[slug];
    drag = { type: "node", slug, sx: e.clientX, sy: e.clientY, ox: p.x, oy: p.y, moved: false };
  } else {
    drag = { type: "pan", sx: e.clientX, sy: e.clientY,
             ox: tfFor().x, oy: tfFor().y, moved: false,
             blob: lbl ? lbl.dataset.slug : null };
  }
  svg.setPointerCapture(e.pointerId);
  svg.classList.add("dragging");
});
svg.addEventListener("pointermove", e => {
  if (!drag) return;
  const dx = e.clientX - drag.sx, dy = e.clientY - drag.sy;
  if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
  if (!drag.moved) return;
  if (drag.type === "pan") {
    const t = tfFor();
    t.x = drag.ox + dx;
    t.y = drag.oy + dy;
    applyTf();
  } else {
    const pos = posFor(), p = pos[drag.slug];
    p.x = drag.ox + dx / tfFor().k;
    p.y = drag.oy + dy / tfFor().k;
    nodeEls[drag.slug].setAttribute("transform", nodeXf(p, bySlug[drag.slug]));
    edges.forEach((eg, i) => {
      if (!edgeEls[i]) return;
      if (eg.from === drag.slug || eg.to === drag.slug)
        edgeEls[i].setAttribute("d", edgePath(eg, pos));
    });
    if (show.blobs && recVis()) updateBlobs(drag.slug);
  }
});
svg.addEventListener("pointerup", e => {
  svg.classList.remove("dragging");
  if (!drag) return;
  if (!drag.moved) {
    if (drag.type === "node") select(drag.slug);
    else if (drag.blob) select(drag.blob);
    else deselect();
  }
  drag = null;
});
svg.addEventListener("wheel", e => {
  e.preventDefault();
  const t = tfFor(), r = svg.getBoundingClientRect();
  const mx = e.clientX - r.left, my = e.clientY - r.top;
  const k2 = Math.min(2.5, Math.max(0.1, t.k * Math.exp(-e.deltaY * 0.0016)));
  t.x = mx - (mx - t.x) * (k2 / t.k);
  t.y = my - (my - t.y) * (k2 / t.k);
  t.k = k2;
  applyTf();
}, { passive: false });
document.addEventListener("keydown", e => { if (e.key === "Escape") deselect(); });

document.getElementById("search").addEventListener("input", e => {
  query = e.target.value.trim().toLowerCase();
  updateDim();
});

// The layout's own scenery is content, not decoration: an empty `broken` column
// is a real answer, and cropping it because it holds no cards would be a lie.
function furnitureBounds(pos) {
  if (show.layout === "timeline") {
    const f = timelineFurniture(pos);
    return f && { minX: f.x0 - 58, maxX: f.x1,
                  minY: f.top - 20, maxY: f.bottom + 18 };
  }
  if (show.layout === "board") {
    const f = boardFurniture();
    if (!f) return null;
    const last = f.columns[f.columns.length - 1];
    return { minX: f.columns[0].x - 12, maxX: last.x + last.w + 12,
             minY: f.headerY - 24, maxY: f.height + 30 };
  }
  if (show.layout === "layered" && show.graphs === "both")
    return { minX: 1e9, maxX: -1e9, minY: -64, maxY: -1e9 };  // column headers
  return null;
}

function worldBounds() {
  const pos = posFor();
  let minX = 1e9, minY = 1e9, maxX = -1e9, maxY = -1e9;
  for (const slug in pos) {
    if (!nodeEls[slug]) continue;
    const entry = bySlug[slug], d = dimsFor(entry);
    const circle = styleFor(entry) === "circle";
    const hx = circle ? R + BPAD + 20 : d.w / 2;
    const hy = circle ? R + BPAD + 20 : d.h / 2;
    minX = Math.min(minX, pos[slug].x - hx);
    maxX = Math.max(maxX, pos[slug].x + hx);
    minY = Math.min(minY, pos[slug].y - hy);
    maxY = Math.max(maxY, pos[slug].y + hy);
  }
  const f = furnitureBounds(pos);
  if (f) {
    minX = Math.min(minX, f.minX); maxX = Math.max(maxX, f.maxX);
    minY = Math.min(minY, f.minY); maxY = Math.max(maxY, f.maxY);
  }
  return { minX, minY, maxX, maxY };
}

// Which axis a layout is fitted on, and how far it may be enlarged.
//
// Fitting both axes of a long strip is what produced the 0.18 zoom this overhaul
// exists to kill. A timeline is short and endless: fit its height, keep the type
// at design size, and scroll through history. Columns and board lanes are the
// same argument turned ninety degrees — fit the width, scroll down the list.
function fitPlan() {
  if (show.layout === "timeline") return { axis: "y", max: 1 };
  if (show.layout === "board") return { axis: "x", max: 1 };
  if (show.layout === "layered" && show.graphs === "both")
    return { axis: "x", max: MAX_FIT };
  return { axis: "both", max: MAX_FIT };
}

// Fit, but never below MIN_FIT. Below that the labels stop being text and the
// view is worthless; scrolling a legible strip beats seeing an illegible whole.
// When the content overflows the axis, anchor at its start rather than centering
// on its middle — for a timeline that means "start at the beginning".
function fit() {
  const { minX, minY, maxX, maxY } = worldBounds();
  if (minX > maxX) return;
  const plan = fitPlan();
  const r = svg.getBoundingClientRect(), pad = 40;
  const kx = (r.width - pad * 2) / (maxX - minX);
  const ky = (r.height - pad * 2) / (maxY - minY);
  const raw = plan.axis === "x" ? kx : plan.axis === "y" ? ky : Math.min(kx, ky);
  const t = tfFor();
  t.k = Math.max(MIN_FIT, Math.min(plan.max, raw));
  const fitsX = (maxX - minX) * t.k <= r.width - pad * 2;
  const fitsY = (maxY - minY) * t.k <= r.height - pad * 2;
  t.x = fitsX ? (r.width - (maxX + minX) * t.k) / 2 : pad - minX * t.k;
  t.y = fitsY ? (r.height - (maxY + minY) * t.k) / 2 : pad - minY * t.k;
  applyTf();
}

// ---------------------------------------------------------------- controls
function syncControls() {
  const active = activePreset();
  document.querySelectorAll("#presets button").forEach(b =>
    b.classList.toggle("active", b.dataset.preset === active));
  document.querySelectorAll("#toggles .seg").forEach(seg => {
    const key = seg.dataset.key;
    seg.querySelectorAll("button").forEach(b =>
      b.classList.toggle("active", b.dataset.val === show[key]));
    // Layout-specific controls are hidden, not dimmed: the panel should only
    // ever offer choices that mean something for what is on screen.
    const only = SEG_FOR_LAYOUT[key];
    seg.hidden = !!only && only.indexOf(show.layout) < 0;
  });
  const both = show.graphs === "both";
  document.querySelectorAll("#toggles .checks input").forEach(cb => {
    const key = cb.dataset.key;
    cb.checked = show[key];
    const off = (key === "impact" || key === "prov") ? !both
      : key === "blobs" ? !recVis() : false;
    cb.disabled = off;
    cb.closest("label").classList.toggle("off", off);
  });
}

// Lanes is about the record graph and Board about the state graph, so picking
// one implies its graph rather than silently rendering an empty canvas.
function setLayout(next) {
  show.layout = next;
  const needs = LAYOUT_GRAPH[next];
  if (needs && show.graphs !== "both" && show.graphs !== needs) show.graphs = needs;
}

// Fit once per arrangement, manual afterward.
function rerender() {
  renderAll();
  const k = layoutKey();
  if (!fitDone[k]) { fit(); fitDone[k] = true; }
}

function applyPreset(name) {
  Object.assign(show, PRESETS[name]);
  syncControls();
  rerender();
}

document.getElementById("controls").addEventListener("click", e => {
  const chip = e.target.closest("#presets button");
  if (chip) { applyPreset(chip.dataset.preset); return; }
  const segBtn = e.target.closest(".seg button");
  if (segBtn) {
    const key = segBtn.closest(".seg").dataset.key;
    if (show[key] !== segBtn.dataset.val) {
      if (key === "layout") setLayout(segBtn.dataset.val);
      else show[key] = segBtn.dataset.val;
      syncControls();
      rerender();
    }
  }
});
document.querySelectorAll("#toggles .checks input").forEach(cb =>
  cb.addEventListener("change", () => {
    show[cb.dataset.key] = cb.checked;
    syncControls();
    rerender();
  }));

// ----------------------------------------------------- resizable sidebar
const side = document.getElementById("side");
const divider = document.getElementById("divider");
let sideWidth = 400, sideCollapsed = false;
function applySide() {
  side.style.width = sideCollapsed ? "0px" : sideWidth + "px";
  divider.classList.toggle("collapsed", sideCollapsed);
}
let sideDrag = null;
divider.addEventListener("pointerdown", e => {
  sideDrag = { sx: e.clientX, moved: false };
  divider.setPointerCapture(e.pointerId);
});
divider.addEventListener("pointermove", e => {
  if (!sideDrag) return;
  if (Math.abs(e.clientX - sideDrag.sx) > 3) sideDrag.moved = true;
  if (!sideDrag.moved) return;
  const w = window.innerWidth - e.clientX - 3;
  if (w < 140) sideCollapsed = true;
  else { sideCollapsed = false; sideWidth = Math.min(640, Math.max(240, w)); }
  applySide();
});
divider.addEventListener("pointerup", () => {
  if (sideDrag && !sideDrag.moved) {  // click (incl. the chevron): toggle
    sideCollapsed = !sideCollapsed;
    applySide();
  }
  sideDrag = null;
});

document.getElementById("fitBtn").addEventListener("click", fit);
document.getElementById("themeBtn").addEventListener("click", () => {
  theme = theme === "light" ? "dark" : "light";
  document.body.dataset.theme = theme;  // also swaps the sun/moon icon via CSS
  renderAll();
  renderPanel();
});
