# LedgerFlow — Graph Canvas UX requirements

**As of:** 2026-04-16
**Status:** draft — input for a dedicated UX sprint. Current implementation at `frontend/src/app/components/GraphView.tsx` is a working scaffold, not the final design.

## Why this doc exists

The graph canvas is the most information-dense surface in LedgerFlow. What works well makes an investigator say "now I see it" in five seconds; what works badly buries the signal under hundreds of uniform nodes. This doc captures the requirements gathered across 2 review sessions so a UX sprint can design against them in one pass.

---

## 1. Purpose of the canvas

A case graph must answer three questions at a glance:

1. **Who is in this case?** — persons, their accounts, the outside entities they transact with.
2. **What's the money doing?** — direction, frequency, volume, time.
3. **What's suspicious?** — which parts of the graph carry forensic flags, outliers, or deserve attention first.

Secondary uses:
- Scope a drill-down to the Workbench (filtered txn list) from a node.
- Build a one-page case export visual.
- Hunt ("is X connected to Y by any path?").

The canvas is **not** the main investigation workspace — the Workbench is. The graph is an orientation + hunting tool.

---

## 2. Node model

Each node is one of four kinds. **Visual hierarchy matters**: accounts and persons are the case's skeleton; entities are context. High-signal entities (a suspected counterparty, a sanctioned name) should look more important than low-signal ones (a payment provider, a utility biller).

### 2.1 Node kinds

| Kind       | Shape     | Default size | Default prominence | Purpose                                          |
|------------|-----------|-------------:|--------------------|--------------------------------------------------|
| Person     | rounded rectangle | L    | High (bold outline, saturated fill) | The subject of the case. Rare; usually 1–3.     |
| Account    | rounded rectangle | L    | High (bank colour coding)           | The person's bank accounts. Money flows *through* these. |
| Entity (named / forensic) | rounded rectangle | M | Medium | A resolved counterparty with a real identity (e.g. a supplier, a person-to-person UPI peer, a flagged entity). |
| Entity (utility / provider) | small pill or circle | S | Low (muted fill, smaller type) | Payment providers, bill collectors, government, known merchants. Noise by default; filterable in. |

### 2.2 Entity sub-type hierarchy

Entities are already classified by the backend (`core.analysis.entity_classification` + `plugins/bank/vocabularies.py`):

| Type            | Visual treatment                                        |
|-----------------|---------------------------------------------------------|
| `counterparty`  | full node, standard weight — the default human-of-interest |
| `merchant`      | smaller node, muted fill (grey/slate)                   |
| `bank`          | smaller node, bank-blue accent                          |
| `government`    | small rounded pill, olive/amber                         |
| `salary`        | small pill, emerald (always a credit source)            |
| `finance`       | small pill, navy                                        |
| `utility`       | smallest pill, slate — barely visible by default        |

This matches the user insight: *"people should be generic, but things like bills, payment providers etc - should be slightly insignificant (possibly round or another type)."*

**Open UX decision:** whether to use actual shape variation (rectangle vs pill vs circle) or just size + colour. Shape variation reads faster; adds layout complexity.

### 2.3 Node sizing

Size encodes volume, not importance:

- **Person / Account node size** = fixed (these are the skeleton).
- **Entity node size** scales with `√(txn_count)`, clamped to a small range (e.g. 40–80px height). Prevents one giant entity from dwarfing the rest.
- **Alternative**: size by `log(total_amount)`. Better signal for money-weight, worse for frequency signal. Sprint should choose one.

### 2.4 Node labels

Two-line format inside every node:
1. **Primary** — the display name (truncated at ~26 chars with ellipsis + full name in tooltip).
2. **Secondary** — one-line meta: `12 txns · ₹3.2L` for entities, `HDFC CC ****1234` for accounts, `Suraj Shyam More` for persons.

Font: Inter 12px/10px for the two lines. Tabular-nums for the numerics.

### 2.5 Node badges

Small corner decorations, independent of size:

- 🚩 **flagged** — red dot top-right if any contributing txn has a pattern flag.
- ✓ **reviewed** — check top-right if the majority of contributing txns are reviewed.
- ⚠ **needs-review** — amber dot if any contributing txn is in `needs_review`.
- 💰 **high-value** — gold dot if this entity's total > some threshold (configurable).

Max one badge at a time, prioritised flagged > needs-review > high-value > reviewed.

---

## 3. Edge model

### 3.1 Edge kinds

| Kind        | Meaning                          | Direction | Default colour    |
|-------------|----------------------------------|-----------|-------------------|
| `owns`      | person → account                 | →         | Slate, thin, dashed |
| `flow_out`  | account → entity (money leaves)  | →         | Destructive red   |
| `flow_in`   | entity → account (money arrives) | →         | Emerald green     |

### 3.2 Edge weighting

- **Thickness** = `min(6px, 1 + log10(total_amount / 1000))`. So ₹1k = 1px, ₹10k = 2px, ₹1L = 3px, ₹10L = 4px, ₹1Cr = 5px. Readable but bounded.
- **Opacity** = 1.0 by default; drops to 0.15 when a non-incident node is selected, or when search filters this edge out.

### 3.3 Edge labels

- Only on flow edges (never on owns).
- Format: `9× · ₹3.2L` — transaction count + total amount, tight font (10px, tabular-nums).
- Show arrowhead at the target end.
- **Open question**: when both flow_in and flow_out exist between the same pair, should they be (a) parallel edges (one up, one down) or (b) one bi-directional edge with split colouring? Crypto shows both. Cleaner visually, but loses the asymmetry when one direction has much more volume.

### 3.4 Edge aggregation — "expand the 9×"

**Today's behaviour** (just shipped): clicking an edge in the Node Inspector expands it inline to show up to 20 contributing transactions, each with date + amount + description. Over 20 → "Open in Workbench" link.

**Desired sprint outcome**: same interaction from the canvas directly, not just the inspector. Click an edge on the canvas → a small floating popover shows the first 5 txns; click "show all N" → opens the inspector to that edge, already expanded. This keeps the fast path (glance) and the deep path (drill-down) both on the canvas.

---

## 4. Layout

### 4.1 Algorithms available

Must let the user switch between three, with a sensible default (`layered`):

| Name       | ELK algo   | When it helps                                             |
|------------|------------|-----------------------------------------------------------|
| Layered    | `layered` (L→R hierarchy) | When you want to read flow direction as a narrative. Default. |
| Stress     | `stress` (organic majorisation) | When you want to see clusters naturally form. Crypto uses this for "organic mode". |
| Radial     | `radial` (hub-and-spoke) | When the case has one clear hub (one account dominating). |

Crypto also has a **Smart mode** that auto-picks based on graph density, hub share, and cycle rate. Worth cloning in Phase 4 — Phase 3 can ship without.

### 4.2 Stacking — "all in on one side, all out on the other"

Requested, high-value visual:

- For a selected account, arrange all its `flow_in` partners on the **left** and `flow_out` partners on the **right**, each column ranked by total amount descending.
- When an entity has both directions → the edge stays bi-directional (parallel arrows, one each side) and the entity is shown once, positioned closer to the stronger direction.
- This is a view mode, not a full layout — toggle via a button "In/Out stacked view". Under the hood, call ELK with fixed node positions we compute ourselves; ELK only routes edges.

### 4.3 Orphan handling

**Shipped today:** hide any node with no incident edges after the amount filter. Toggle in the filter bar.

**Sprint ask**: orphans shouldn't be invisible — show a small "+ 237 hidden entities" chip at the top-right with a click-through to reveal them.

### 4.4 Sizing the canvas

The canvas takes 72vh of the workbench tab. With the inspector open, the canvas is ~ (viewport - 520px). Sprint should test at 1280×720 (smallest supported) and ensure nothing overlaps.

---

## 5. Interaction model

### 5.1 Selection

- **Click a node** → opens inspector; dims non-incident edges to 12% opacity.
- **Click empty canvas** → clears selection.
- **Shift-click** → multi-select (not yet shipped). Goal: compare two entities side-by-side in the inspector, or sum stats.
- **Double-click a node** → zoom to fit that node + its direct neighbours.

### 5.2 Hover

- **Hover a node** → show full label + one-line stats in a tooltip. No inspector. 200ms delay to avoid flicker.
- **Hover an edge** → show `9× · ₹3.2L · Aug 2021 → Jun 2024`.

### 5.3 Search

**Shipped today**: text input in the filter bar. Typing dims non-matching nodes/edges to 25%.

**Sprint extension**:
- Enter key → pan + zoom to fit all matches.
- Results count in the input: `Find entity… (3 matches)`.
- Fuzzy match (tokenised) — today we do substring.

### 5.4 Pan / zoom

Standard react-flow controls (wheel to zoom, drag to pan). Add a "Fit all" button next to the layout dropdown.

### 5.5 Drag

All nodes are draggable. After manual positioning, lock positions (don't re-layout on filter change). A "Re-run layout" button reverts to auto-layout.

### 5.6 Node inspector — the side panel

Shipped today: 520px right-side panel, shows type, meta, flow-in/out KPIs, expandable edges with contributing txns, "Open in Workbench" link.

**Sprint asks**:
- Make the inspector **resizable** (drag handle between canvas and panel).
- Tabs for `Overview / Flows / Transactions / Pattern hits / Related entities` (crypto's NodeInspector uses tabs).
- "Mark entity reviewed" / "Flag entity" actions at the bottom, writing to all incident transactions.

### 5.7 Edge click

Not implemented. Sprint: clicking an edge selects both endpoints and opens the inspector scoped to this one edge.

---

## 6. Filters

Current filter bar (shipped):
- Search
- Node type (persons / accounts / entities)
- Min flow amount (₹0, ₹1k, ₹10k, ₹50k, ₹1L, ₹5L)
- Hide orphans toggle
- Layout (layered / stress / radial)

**Sprint additions**:
- **Date range** — shrink the graph to a window. Bar chart preview of txn density by month, brushable. Essential for large cases.
- **Entity type** — persons vs merchants vs bills etc.; each a separate checkbox group.
- **Flagged only** — show only edges/entities with at least one forensic pattern hit.
- **Min txn count** — "hide entities with fewer than 3 txns".
- **Saved filter presets** — "investigation view", "export view".

---

## 7. Visual system

### 7.1 Colour

Forensic Ledger palette:
- Navy `--fl-navy-500` = person, primary edges
- Teal `--fl-teal-500` = account
- Slate `--fl-slate-200` / 400 = entity (neutral)
- Red `--fl-ruby-500` = flow_out, high severity
- Emerald `--fl-emerald-500` = flow_in, low severity / salary / reviewed
- Amber = warnings / needs review
- Type-specific accents for entities (see 2.2)

### 7.2 Typography

- Node primary label: Inter 600 12px
- Node secondary meta: Inter 400 10px
- Edge label: Inter 500 10px, tabular
- Inspector body: Inter 400 13px, tabular-nums on numerics

### 7.3 Transparency

- Dimmed node: `opacity: 0.25` (search miss) or `0.12` (selection non-incident).
- Dimmed edge: `opacity: 0.12`.
- Never fully hide — dimmed means "not focus", not "gone".

---

## 8. Performance

Current seed case: 289 nodes, 311 edges. Comfortable. Worst case expected: 2,000 nodes, 8,000 edges (a big FIR with 20 accounts × 100 entities each).

Requirements:
- ELK layout must complete within 3s at 2,000 nodes.
- Pan / zoom must stay 60fps.
- Dragging a node must not trigger a relayout.
- Search / filter must apply within 300ms (client-side).

Known risk: react-flow's default rendering gets slow above ~1,000 visible edges. Sprint should evaluate:
- Edge bundling (combine parallel edges into one thicker one).
- Level-of-detail (hide labels below certain zoom; hide nodes below certain size).
- Virtualisation (only render nodes inside the viewport).

---

## 9. Accessibility

- Keyboard: tab to focus the first node, arrow keys to walk the graph, Enter to open inspector, Esc to close.
- Colour-blind: never convey direction by colour alone — always pair with arrowhead + shape.
- Screen reader: every node has an aria-label with its full name + type + stats.

---

## 10. Export

- Export the current viewport as PNG / SVG / PDF.
- Export the filtered graph data as JSON (for case reports).
- Copy-to-clipboard for a specific node's meta.

---

## 11. Out-of-scope (Phase 4+)

- Multi-case graphs (cross-case entity linking).
- Temporal animation (slider that plays back txn flow over time).
- Geographic overlay (map the accounts' branch locations).
- Pattern-path highlighting (visualise a full structuring pattern as a lit-up sub-graph).

---

## 12. What's shipped vs. what's not (as of commit 7a1bc7d)

### Shipped
- ELK layout with 3 algorithms (layered default)
- Draggable nodes, zoom/pan, minimap
- Colour-coded edges (direction), log-scaled thickness, arrowheads
- Click-to-inspect with 520px split-pane side panel
- Inspector shows type, meta, KPIs, all incident edges (sorted by amount)
- Inspector edge rows expand inline to show up to 20 contributing txns (date + amount + description)
- Filters: node type, min-flow, hide orphans, layout
- Search bar with dim-on-miss
- Entity type classification (merchant / salary / finance / gov / bank / utility) via the `core/` import

### Not shipped (sprint output)
- Node visual hierarchy by entity sub-type (sizes, shapes, muted utility nodes)
- In/Out stacked view
- Date-range filter
- Flagged-only filter
- Multi-select via Shift-click
- Edge-click selection and floating popover
- Hover tooltips with rich content
- Inspector tabs (Overview / Flows / Transactions / Pattern hits / Related)
- Inspector resize handle
- Smart-mode auto layout
- "Fit all" button
- Export to PNG / SVG
- Saved filter presets
- Level-of-detail rendering for large graphs
