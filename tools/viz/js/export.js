const exportMenu = document.getElementById("exportMenu");
document.getElementById("exportBtn").addEventListener("click", e => {
  e.stopPropagation();
  exportMenu.hidden = !exportMenu.hidden;
});
document.addEventListener("click", e => {
  if (!exportMenu.hidden && !(e.target.closest && e.target.closest("#exportWrap")))
    exportMenu.hidden = true;
});
document.getElementById("printBtn").addEventListener("click", () => {
  exportMenu.hidden = true;
  fit();
  setTimeout(() => window.print(), 60);
});
// The exported SVG is standalone: every mark is styled by attribute, not by a
// stylesheet, so it survives being dropped into a document or an editor.
function exportSvg() {
  // worldBounds already accounts for each layout's own scenery — lane rules and
  // the date gutter, board column headers, the two-column captions — so every
  // view exports whole instead of only the four that predate them.
  const { minX, minY, maxX, maxY } = worldBounds();
  if (minX > maxX) return null;
  // A file has no zoom, so it gets full detail regardless of the current one.
  const k = tfFor().k;
  applyLod(Infinity);
  const pad = 40;
  const w = maxX - minX + pad * 2, h = maxY - minY + pad * 2;
  const out = el("svg", { xmlns: SVGNS, width: w, height: h,
    viewBox: `${minX - pad} ${minY - pad} ${w} ${h}`, "font-family": FONT });
  out.appendChild(el("rect", { x: minX - pad, y: minY - pad, width: w, height: h,
    fill: T().page }));
  out.appendChild(markerDefs());
  const world = document.getElementById("world").cloneNode(true);
  world.removeAttribute("transform");
  out.appendChild(world);
  applyLod(k);
  return new XMLSerializer().serializeToString(out);
}

document.getElementById("svgBtn").addEventListener("click", () => {
  exportMenu.hidden = true;
  const text = exportSvg();
  if (!text) return;
  const blob = new Blob([text], { type: "image/svg+xml" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${DATA.project}-${activePreset() || "custom"}.svg`;
  a.click();
  URL.revokeObjectURL(a.href);
});

