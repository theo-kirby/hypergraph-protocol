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
document.getElementById("svgBtn").addEventListener("click", () => {
  exportMenu.hidden = true;
  let { minX, minY, maxX, maxY } = worldBounds();
  if (minX > maxX) return;
  if (show.layout === "layered" && show.graphs === "both") minY -= 80;  // headers
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
  const blob = new Blob([new XMLSerializer().serializeToString(out)],
    { type: "image/svg+xml" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${DATA.project}-${activePreset() || "custom"}.svg`;
  a.click();
  URL.revokeObjectURL(a.href);
});

