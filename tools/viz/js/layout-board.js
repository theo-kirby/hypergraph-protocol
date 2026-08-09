// ------------------------------------------------------------------- board
// The state graph is a status board, not a graph. Twelve nodes at depth 2 drawn
// as a tree is a flat bar in an empty screen — and it is the view that carries
// the frontier, which is the first thing an arriving reader needs.
//
// Columns run broken | blocked | open | working | superseded: the three frontier
// statuses first, because "what is broken or waiting" outranks "what is fine".
// An empty column is kept and labelled 0 — "nothing is broken" is a real answer.

const BOARD_COLUMNS = ["broken", "blocked", "open", "working", "superseded"];
// Positions are card *centres*, so the first row must clear the header band.
const BOARD_HEAD = 0;                    // header text baseline
const BOARD_TOP = BH / 2 + 18;           // first card's centre
const TREE_INDENT = 34;
// An empty column collapses to a rail instead of vanishing. "Nothing is broken"
// still gets said, and the five statuses stop costing 1290px of width when only
// two of them hold anything.
const RAIL_W = 52, RAIL_GAP = 12;

function boardCards() {
  return DATA.state.nodes.filter(n => !n.is_root);
}
function boardRoot() {
  return DATA.state.nodes.find(n => n.is_root) || null;
}

// Freshest first inside a column: `last_record_at` is the newest record node
// cited as this claim's provenance, so the column reads newest work downward.
function boardColumnOrder(a, b) {
  const at = a.last_record_at || "", bt = b.last_record_at || "";
  if (at !== bt) return at < bt ? 1 : -1;
  return a.seq - b.seq;
}

function boardGroups() {
  const groups = {};
  BOARD_COLUMNS.forEach(s => groups[s] = []);
  boardCards().forEach(n => (groups[n.status] || (groups[n.status] = [])).push(n));
  BOARD_COLUMNS.forEach(s => groups[s].sort(boardColumnOrder));
  return groups;
}

// Column geometry: x and width per status, wide when populated, a rail when not.
function boardColumns() {
  const groups = boardGroups();
  let x = 0;
  return BOARD_COLUMNS.map(status => {
    const count = groups[status].length;
    const w = count ? BW : RAIL_W;
    const col = { status, count, nodes: groups[status], x, w, rail: !count };
    x += w + (count ? BCOL - BW : RAIL_GAP);
    return col;
  });
}

function layoutBoard(pos) {
  const root = boardRoot();
  if (show.board === "tree") {
    // Mirrors STATE.md's Architecture section: pre-order DFS (`seq`) with the
    // graph depth (`layer`) as indentation.
    DATA.state.nodes.forEach(n => pos[n.slug] = {
      x: n.layer * TREE_INDENT + BW / 2,
      y: n.seq * (BH + 10),
    });
  } else {
    const cols = boardColumns();
    cols.forEach(col => col.nodes.forEach((n, row) => pos[n.slug] = {
      x: col.x + BW / 2,
      y: BOARD_TOP + row * BROW,
    }));
    const last = cols[cols.length - 1];
    if (root) pos[root.slug] = {   // the root is a caption, not a column item
      x: (cols[0].x + last.x + last.w) / 2,
      y: BOARD_HEAD - 26 - BH / 2,
    };
  }
  if (recVis()) {  // record visible alongside: a chronological column to the left
    const left = -BCOL - NW / 2 - 40;
    recordChrono().forEach(n => pos[n.slug] = { x: left, y: n.chrono * (NH + 16) });
  }
  return pos;
}

// Column headers, drawn only in status mode. Counts come from the same grouping
// the layout used, so a header can never disagree with its column.
function boardFurniture() {
  if (show.board !== "status") return null;
  const columns = boardColumns();
  const rows = Math.max(1, ...columns.map(c => c.count));
  return { columns, headerY: BOARD_HEAD,
           height: BOARD_TOP + (rows - 1) * BROW + BH / 2 + 14 };
}
