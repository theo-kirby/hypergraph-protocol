// -------------------------------------------------------------------- boot
// Deep links: #timeline | #frontier | #provenance | #clusters | #everything
// selects that view (the pre-rename hashes #record #state #combo #combination
// #hyper still work, see VIEW_ALIASES); #<slug> jumps to a node.
document.body.dataset.theme = theme;
applySide();
registerPucks();   // synthetic entries for collapsed hyperedges
buildTagChips();   // no-op on a graph that carries no tags
initTuning();      // BLOB gets its config/stored values before anything is drawn
const boot = decodeURIComponent(location.hash.slice(1));
const bootView = VIEW_ALIASES[boot] || boot;
// Default to everything on: show what is in the graph first, then let the four
// focused views take things away. One click, or one number key, gets there.
applyPreset(PRESETS[bootView] ? bootView : "everything");
if (bySlug[boot]) jumpTo(boot);
renderPanel();
startLive();   // no-op unless `viz --live` set DATA.live
