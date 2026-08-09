// -------------------------------------------------------------------- boot
// Deep links: #timeline | #frontier | #provenance | #clusters selects that view
// (the pre-rename hashes #record #state #combo #combination #hyper still work,
// see VIEW_ALIASES); #<slug> jumps to a node.
document.body.dataset.theme = theme;
applySide();
const boot = decodeURIComponent(location.hash.slice(1));
const bootView = VIEW_ALIASES[boot] || boot;
applyPreset(PRESETS[bootView] ? bootView : "clusters");
if (bySlug[boot]) jumpTo(boot);
renderPanel();
startLive();   // no-op unless `viz --live` set DATA.live
