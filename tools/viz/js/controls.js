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
    nodeEls[drag.slug].setAttribute("transform", nodeXf(p));
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

function worldBounds() {
  const pos = posFor();
  const circles = show.style === "circles";
  const hx = circles ? R + BPAD + 20 : NW / 2;
  const hy = circles ? R + BPAD + 20 : NH / 2;
  let minX = 1e9, minY = 1e9, maxX = -1e9, maxY = -1e9;
  for (const slug in pos) {
    if (!nodeEls[slug]) continue;
    minX = Math.min(minX, pos[slug].x - hx);
    maxX = Math.max(maxX, pos[slug].x + hx);
    minY = Math.min(minY, pos[slug].y - hy);
    maxY = Math.max(maxY, pos[slug].y + hy);
  }
  return { minX, minY, maxX, maxY };
}

function fit() {
  let { minX, minY, maxX, maxY } = worldBounds();
  if (minX > maxX) return;
  if (show.layout === "layered" && show.graphs === "both") minY -= 60;  // column headers
  const r = svg.getBoundingClientRect(), pad = 50;
  const t = tfFor();
  t.k = Math.min(1.25, (r.width - pad * 2) / (maxX - minX),
                 (r.height - pad * 2) / (maxY - minY));
  t.x = (r.width - (maxX + minX) * t.k) / 2;
  t.y = (r.height - (maxY + minY) * t.k) / 2;
  applyTf();
}

// ---------------------------------------------------------------- controls
function syncControls() {
  const active = activePreset();
  document.querySelectorAll("#presets button").forEach(b =>
    b.classList.toggle("active", b.dataset.preset === active));
  document.querySelectorAll("#toggles .seg").forEach(seg => {
    seg.querySelectorAll("button").forEach(b =>
      b.classList.toggle("active", b.dataset.val === show[seg.dataset.key]));
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
      show[key] = segBtn.dataset.val;
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
