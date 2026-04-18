import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  useReactFlow,
  type Node,
  type Edge,
  type NodeMouseHandler,
  type EdgeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import ELK from "elkjs/lib/elk.bundled.js";
import {
  Filter, Loader2, X, ExternalLink, Search, ChevronDown, ChevronRight,
  Maximize2, Flag,
} from "lucide-react";
import { useCaseGraph, usePatchTransaction } from "../lib/queries";
import type { GraphNode, GraphEdge, GraphEdgeSample } from "../lib/api";
import { PersonNode } from "./graph/PersonNode";
import { AccountNode } from "./graph/AccountNode";
import { EntityNode } from "./graph/EntityNode";
import { FlowEdge } from "./graph/FlowEdge";

const NODE_TYPES = {
  person: PersonNode,
  account: AccountNode,
  entity: EntityNode,
} as const;

const EDGE_TYPES = {
  owns: FlowEdge,
  flow_in: FlowEdge,
  flow_out: FlowEdge,
} as const;

// ELK bounding boxes per node kind. Kept in sync with the min-width used in
// the custom node components so edge routing doesn't overshoot/underhang.
function elkSizeFor(n: GraphNode): { width: number; height: number } {
  if (n.type === "person") return { width: 220, height: 58 };
  if (n.type === "account") return { width: 240, height: 58 };
  const sub = String(n.meta?.entity_type || "counterparty");
  const w =
    sub === "utility" ? 140 :
    sub === "government" || sub === "salary" ? 160 :
    sub === "counterparty" ? 200 :
    180;
  return { width: w, height: 50 };
}

interface GraphViewProps {
  caseId: string;
}

const elk = new ELK();

// Used by the inspector + minimap (not by the custom node renderers).
const PALETTE = {
  person:  { bg: "var(--fl-navy-800)", text: "#fff", border: "var(--fl-navy-700)" },
  account: { bg: "#0e7490", text: "#fff", border: "#0891b2" },
  entity:  { bg: "#475569", text: "#fff", border: "#64748b" },
};

// Minimap uses raw hex — CSS vars don't resolve inside the SVG context here.
const MINIMAP_COLOR = {
  person:  "#002046",
  account: "#0e7490",
  entity:  "#475569",
};

type LayoutMode = "layered" | "stress" | "radial";

const ELK_ALGORITHMS: Record<LayoutMode, Record<string, string>> = {
  layered: {
    "elk.algorithm": "layered",
    "elk.direction": "RIGHT",
    "elk.layered.spacing.nodeNodeBetweenLayers": "140",
    "elk.spacing.nodeNode": "60",
    "elk.layered.nodePlacement.strategy": "BRANDES_KOEPF",
    "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
    "elk.layered.edgeRouting": "ORTHOGONAL",
    "elk.layered.thoroughness": "10",
  },
  // Stress (majorisation) converges more reliably than `force` on the
  // bank-case graph, and is what the crypto team uses for organic mode.
  stress: {
    "elk.algorithm": "stress",
    "elk.stress.desiredEdgeLength": "240",
    "elk.stress.iterationLimit": "500",
    "elk.spacing.nodeNode": "80",
  },
  radial: {
    "elk.algorithm": "radial",
    "elk.radial.radius": "260",
    "elk.spacing.nodeNode": "60",
  },
};

function formatINR(n: number): string {
  if (n >= 10_000_000) return `₹${(n / 10_000_000).toFixed(1)}Cr`;
  if (n >= 100_000) return `₹${(n / 100_000).toFixed(1)}L`;
  if (n >= 1_000) return `₹${(n / 1_000).toFixed(0)}k`;
  return `₹${n.toFixed(0)}`;
}

// Manually compute positions for the "In/Out stacked view". The anchor is
// centred; its flow_in partners stack in a left column ranked by total_amount
// desc, flow_out partners in a right column same ranking. Anything else on
// canvas (other persons, orphan entities) lines up far left/right so it
// doesn't crash the composition — we're optimising for the anchor's story.
function computeStackedLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  anchor: GraphNode,
): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();

  const COL_GAP = 420;   // horizontal distance from anchor to each column
  const ROW_GAP = 74;    // vertical gap between stacked partners

  // Sum in/out amounts to each partner (accounts may also be partners of an
  // entity anchor and vice-versa). A partner in both directions is placed
  // wherever its net absolute weight is heavier.
  const partnerAmount: Map<string, { inAmt: number; outAmt: number }> = new Map();
  for (const e of edges) {
    if (e.kind === "owns") continue;
    const isIncoming = e.target === anchor.id;
    const isOutgoing = e.source === anchor.id;
    if (!isIncoming && !isOutgoing) continue;
    const partner = isIncoming ? e.source : e.target;
    const rec = partnerAmount.get(partner) ?? { inAmt: 0, outAmt: 0 };
    if (isIncoming) rec.inAmt += e.total_amount;
    else rec.outAmt += e.total_amount;
    partnerAmount.set(partner, rec);
  }

  const leftCol: Array<[string, number]> = [];
  const rightCol: Array<[string, number]> = [];
  for (const [id, { inAmt, outAmt }] of partnerAmount) {
    if (inAmt >= outAmt) leftCol.push([id, inAmt]);
    else rightCol.push([id, outAmt]);
  }
  leftCol.sort((a, b) => b[1] - a[1]);
  rightCol.sort((a, b) => b[1] - a[1]);

  // Anchor in the middle.
  positions.set(anchor.id, { x: 0, y: 0 });

  const placeColumn = (col: Array<[string, number]>, x: number) => {
    const n = col.length;
    const topY = -((n - 1) * ROW_GAP) / 2;
    col.forEach(([id], i) => {
      positions.set(id, { x, y: topY + i * ROW_GAP });
    });
  };
  placeColumn(leftCol, -COL_GAP);
  placeColumn(rightCol, COL_GAP);

  // Any remaining nodes (unrelated to the anchor) get parked far away so they
  // don't interfere visually — behind the columns, stacked vertically.
  let parkY = 600;
  for (const n of nodes) {
    if (positions.has(n.id)) continue;
    positions.set(n.id, { x: -COL_GAP * 2.2, y: parkY });
    parkY += 60;
  }
  return positions;
}

async function computeElkLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  mode: LayoutMode,
): Promise<Map<string, { x: number; y: number }>> {
  const elkGraph = {
    id: "root",
    layoutOptions: ELK_ALGORITHMS[mode],
    children: nodes.map((n) => ({ id: n.id, ...elkSizeFor(n) })),
    edges: edges.map((e) => ({ id: e.id, sources: [e.source], targets: [e.target] })),
  };
  const layout = await elk.layout(elkGraph as any);
  const positions = new Map<string, { x: number; y: number }>();
  for (const child of layout.children ?? []) {
    positions.set(child.id as string, { x: (child as any).x ?? 0, y: (child as any).y ?? 0 });
  }
  return positions;
}

function nodeSublabel(n: GraphNode): string {
  if (n.type === "person") {
    const pan = n.meta?.pan ? `PAN ${n.meta.pan}` : "";
    return [`${n.size} account${n.size === 1 ? "" : "s"}`, pan].filter(Boolean).join(" · ");
  }
  if (n.type === "account") {
    return `${n.size} txn${n.size === 1 ? "" : "s"}`;
  }
  return `${n.size} txn${n.size === 1 ? "" : "s"}`;
}

// `focus` describes what the user currently has selected. When present, any
// node/edge outside it is dimmed. Used for both node-click and edge-click.
type FocusSet = { nodes: Set<string>; edges: Set<string> } | null;

function buildEdges(
  edges: GraphEdge[],
  focus: FocusSet,
  matchSet: Set<string> | null,
  selectedEdgeId: string | null,
): Edge[] {
  return edges.map((e) => {
    const selDim = focus ? !focus.edges.has(e.id) : false;
    const searchDim = matchSet ? !(matchSet.has(e.source) || matchSet.has(e.target)) : false;
    const dim = Boolean(selDim || searchDim);
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      type: e.kind,
      selected: e.id === selectedEdgeId,
      data: {
        totalAmount: e.total_amount,
        txnCount: e.txn_count,
        dim,
      },
    } as Edge;
  });
}

export function GraphView({ caseId }: GraphViewProps) {
  return (
    <ReactFlowProvider>
      <GraphViewInner caseId={caseId} />
    </ReactFlowProvider>
  );
}

function GraphViewInner({ caseId }: GraphViewProps) {
  const { data, isLoading, error } = useCaseGraph(caseId);

  const [showPersons, setShowPersons] = useState(true);
  const [showAccounts, setShowAccounts] = useState(true);
  const [showEntities, setShowEntities] = useState(true);
  const [minAmount, setMinAmount] = useState(50_000);
  const [hideOrphans, setHideOrphans] = useState(true);
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  // Date range: "" means no bound. Format YYYY-MM. Filters flow edges whose
  // [date_min, date_max] window overlaps [dateFrom, dateTo].
  const [dateFrom, setDateFrom] = useState<string>("");
  const [dateTo, setDateTo] = useState<string>("");
  const [layout, setLayout] = useState<LayoutMode>("layered");
  // In/Out stacked view mode (ux §4.2). When enabled AND a node is selected,
  // pins all its flow_in partners in a left column and flow_out partners in
  // a right column, each sorted by total_amount desc. Overrides ELK layout
  // for that frame only — unpinning (toggle off) returns to ELK.
  const [stackedMode, setStackedMode] = useState(false);
  const [selectedNodes, setSelectedNodes] = useState<GraphNode[]>([]);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);
  const selectedNode = selectedNodes[0] ?? null;
  const compareNode = selectedNodes[1] ?? null;
  const [layingOut, setLayingOut] = useState(false);
  const [search, setSearch] = useState("");
  const [inspectorWidth, setInspectorWidth] = useState(520);

  const rf = useReactFlow();

  const [rfNodes, setRfNodes, onNodesChange] = useNodesState<Node>([]);
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState<Edge>([]);

  const filtered = useMemo(() => {
    if (!data) {
      return { nodes: [] as GraphNode[], edges: [] as GraphEdge[], hiddenOrphanCount: 0 };
    }
    let nodes = data.nodes.filter((n) => {
      if (n.type === "person") return showPersons;
      if (n.type === "account") return showAccounts;
      if (n.type === "entity") return showEntities;
      return true;
    });
    if (flaggedOnly) {
      nodes = nodes.filter((n) => n.type === "person" || Boolean(n.meta?.flagged));
    }
    let nodeIds = new Set(nodes.map((n) => n.id));
    const fromStr = dateFrom ? `${dateFrom}-01` : "";
    const toStr = dateTo ? `${dateTo}-31` : "";
    const edges = data.edges.filter((e) => {
      if (!nodeIds.has(e.source) || !nodeIds.has(e.target)) return false;
      if (e.kind === "owns") return true;
      if (e.total_amount < minAmount) return false;
      // Overlap check: edge activity [date_min, date_max] intersects window.
      if (fromStr || toStr) {
        const emin = e.date_min || "";
        const emax = e.date_max || "";
        if (toStr && emin && emin > toStr) return false;
        if (fromStr && emax && emax < fromStr) return false;
      }
      return true;
    });

    // Hide orphans: any node with no incident edges after the amount filter.
    // Persons are always kept if their accounts are visible — otherwise the
    // case's root disappears even when the money flows out of its accounts.
    let hiddenOrphanCount = 0;
    if (hideOrphans) {
      const incident = new Set<string>();
      for (const e of edges) { incident.add(e.source); incident.add(e.target); }
      const before = nodes.length;
      nodes = nodes.filter((n) => incident.has(n.id));
      hiddenOrphanCount = before - nodes.length;
      nodeIds = new Set(nodes.map((n) => n.id));
    }

    return { nodes, edges, hiddenOrphanCount };
  }, [data, showPersons, showAccounts, showEntities, minAmount, hideOrphans, flaggedOnly, dateFrom, dateTo]);

  // Match-set for the search input. Empty string → no dimming.
  const matchSet = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return null;
    const hits = new Set<string>();
    for (const n of filtered.nodes) {
      if (n.label.toLowerCase().includes(q)) hits.add(n.id);
    }
    return hits;
  }, [search, filtered.nodes]);

  // Focus = what's currently selected on the canvas. An edge click focuses
  // just that edge + its two endpoints; a node click focuses the node(s) and
  // all their incident edges (plus the far-side nodes so the connections
  // read). With multi-select, focus is the union of each selected node's
  // incident set.
  const focus: FocusSet = useMemo(() => {
    if (selectedEdge) {
      return {
        nodes: new Set<string>([selectedEdge.source, selectedEdge.target]),
        edges: new Set<string>([selectedEdge.id]),
      };
    }
    if (selectedNodes.length > 0 && data) {
      const nodes = new Set<string>(selectedNodes.map((n) => n.id));
      const edges = new Set<string>();
      const selIds = new Set(selectedNodes.map((n) => n.id));
      for (const e of data.edges) {
        if (selIds.has(e.source) || selIds.has(e.target)) {
          edges.add(e.id);
          nodes.add(e.source);
          nodes.add(e.target);
        }
      }
      return { nodes, edges };
    }
    return null;
  }, [selectedNodes, selectedEdge, data]);

  // (Re-)compute layout whenever filtered graph or mode changes. If stacked
  // mode is on and a node is selected, pin positions manually; otherwise use
  // ELK with the chosen algorithm.
  useEffect(() => {
    if (!filtered.nodes.length) {
      setRfNodes([]);
      setRfEdges([]);
      return;
    }
    let cancelled = false;
    setLayingOut(true);
    const anchor = stackedMode && selectedNode
      ? filtered.nodes.find((n) => n.id === selectedNode.id)
      : null;
    const positionsPromise = anchor
      ? Promise.resolve(computeStackedLayout(filtered.nodes, filtered.edges, anchor))
      : computeElkLayout(filtered.nodes, filtered.edges, layout);
    positionsPromise
      .then((positions) => {
        if (cancelled) return;
        const next: Node[] = filtered.nodes.map((n) => {
          const pos = positions.get(n.id) ?? { x: 0, y: 0 };
          const dim = matchSet ? !matchSet.has(n.id) : false;
          return {
            id: n.id,
            type: n.type,
            position: pos,
            data: {
              label: n.label,
              sublabel: nodeSublabel(n),
              entityType: n.meta?.entity_type,
              accountType: n.meta?.type,
              flagged: Boolean(n.meta?.flagged),
              needsReview: Boolean(n.meta?.needs_review),
              highValue: Boolean(n.meta?.high_value),
              flaggedCount: Array.isArray(n.meta?.flagged_txn_ids) ? n.meta.flagged_txn_ids.length : 0,
              totalAmount: typeof n.meta?.total_amount === "number" ? n.meta.total_amount : undefined,
              dim,
            },
            draggable: true,
          };
        });
        setRfNodes(next);
        setRfEdges(buildEdges(filtered.edges, focus, matchSet, selectedEdge?.id ?? null));
      })
      .catch((e) => console.error("layout failed:", e))
      .finally(() => { if (!cancelled) setLayingOut(false); });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtered, layout, stackedMode, selectedNode?.id]);

  // Re-apply highlight/selection overlays when selection or search changes
  // without re-laying out.
  useEffect(() => {
    setRfNodes((prev) =>
      prev.map((n) => {
        const searchDim = matchSet ? !matchSet.has(n.id) : false;
        const selDim = focus ? !focus.nodes.has(n.id) : false;
        return { ...n, data: { ...(n.data as object), dim: searchDim || selDim } };
      }),
    );
    setRfEdges(buildEdges(filtered.edges, focus, matchSet, selectedEdge?.id ?? null));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus, matchSet]);

  const onNodeClick: NodeMouseHandler = useCallback((evt, node) => {
    const gn = data?.nodes.find((n) => n.id === node.id);
    if (!gn) return;
    setSelectedEdge(null);
    // Shift-click: toggle this node in/out of the compare slot. Non-shift:
    // replace selection with just this node.
    if (evt.shiftKey) {
      setSelectedNodes((prev) => {
        if (prev.some((n) => n.id === gn.id)) {
          // Deselect this node from the compare set.
          return prev.filter((n) => n.id !== gn.id);
        }
        if (prev.length === 0) return [gn];
        // Keep the first (anchor) node, replace/add the second.
        return [prev[0], gn];
      });
    } else {
      setSelectedNodes([gn]);
    }
  }, [data]);

  const onEdgeClick: EdgeMouseHandler = useCallback((_e, edge) => {
    const ge = data?.edges.find((x) => x.id === edge.id);
    if (ge) {
      setSelectedEdge(ge);
      setSelectedNodes([]);
    }
  }, [data]);

  const clearSelection = useCallback(() => {
    setSelectedNodes([]);
    setSelectedEdge(null);
  }, []);

  // Fit view to all visible nodes, or to the current search matches if any.
  const fitAll = useCallback(() => {
    rf.fitView({ padding: 0.15, duration: 300 });
  }, [rf]);

  const zoomToMatches = useCallback(() => {
    if (!matchSet || matchSet.size === 0) {
      rf.fitView({ padding: 0.15, duration: 300 });
      return;
    }
    const ids = Array.from(matchSet).map((id) => ({ id }));
    rf.fitView({ nodes: ids, padding: 0.25, duration: 400 });
  }, [rf, matchSet]);

  // Flagged node count for the "Flagged only" toggle label.
  const flaggedNodeCount = useMemo(() => {
    if (!data) return 0;
    return data.nodes.filter((n) => Boolean(n.meta?.flagged)).length;
  }, [data]);

  if (isLoading) return <div className="bg-card border border-border rounded-lg p-8 text-muted-foreground">Loading graph…</div>;
  if (error) return <div className="bg-destructive/10 border border-destructive/40 rounded-lg p-6 text-destructive">Failed to load graph: {String(error)}</div>;
  if (!data) return null;

  return (
    <div className="space-y-3">
      {/* Filter bar */}
      <div className="bg-card border border-border rounded-lg p-3 flex items-center gap-4 flex-wrap text-sm">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") zoomToMatches(); }}
            placeholder="Find entity / account…  (Enter to zoom)"
            className="pl-8 pr-6 py-1.5 border border-border rounded text-sm w-64 focus:outline-none focus:ring-1 focus:ring-primary"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              className="absolute right-1.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <Filter className="w-4 h-4" />
          Nodes
        </div>
        <label className="flex items-center gap-1.5">
          <input type="checkbox" checked={showPersons} onChange={(e) => setShowPersons(e.target.checked)} />
          <span className="text-foreground">Persons ({data.nodes.filter(n => n.type === "person").length})</span>
        </label>
        <label className="flex items-center gap-1.5">
          <input type="checkbox" checked={showAccounts} onChange={(e) => setShowAccounts(e.target.checked)} />
          <span className="text-foreground">Accounts ({data.nodes.filter(n => n.type === "account").length})</span>
        </label>
        <label className="flex items-center gap-1.5">
          <input type="checkbox" checked={showEntities} onChange={(e) => setShowEntities(e.target.checked)} />
          <span className="text-foreground">Entities ({data.nodes.filter(n => n.type === "entity").length})</span>
        </label>
        <div className="h-5 w-px bg-border" />
        <label className="flex items-center gap-2">
          <span className="text-muted-foreground">Layout:</span>
          <select
            value={layout}
            onChange={(e) => setLayout(e.target.value as LayoutMode)}
            className="px-2 py-1 border border-border rounded text-sm bg-card"
          >
            <option value="layered">Layered (L→R hierarchy)</option>
            <option value="stress">Stress (organic)</option>
            <option value="radial">Radial</option>
          </select>
        </label>
        <label className="flex items-center gap-2">
          <span className="text-muted-foreground">Min flow:</span>
          <select
            value={minAmount}
            onChange={(e) => setMinAmount(Number(e.target.value))}
            className="px-2 py-1 border border-border rounded text-sm bg-card"
          >
            <option value={0}>₹0 (all)</option>
            <option value={1000}>₹1k</option>
            <option value={10000}>₹10k</option>
            <option value={50000}>₹50k</option>
            <option value={100000}>₹1L</option>
            <option value={500000}>₹5L</option>
          </select>
        </label>
        <label className="flex items-center gap-1.5" title="Hide nodes with no visible connections after filtering">
          <input type="checkbox" checked={hideOrphans} onChange={(e) => setHideOrphans(e.target.checked)} />
          <span className="text-foreground">Hide orphans</span>
          {hideOrphans && filtered.hiddenOrphanCount > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground tabular-nums">
              +{filtered.hiddenOrphanCount} hidden
            </span>
          )}
        </label>
        <label
          className="flex items-center gap-1.5"
          title="Only show flagged nodes (those with pattern hits or manual flags)"
        >
          <input type="checkbox" checked={flaggedOnly} onChange={(e) => setFlaggedOnly(e.target.checked)} />
          <Flag className="w-3.5 h-3.5 text-[color:var(--fl-ruby-500)]" />
          <span className="text-foreground">Flagged only ({flaggedNodeCount})</span>
        </label>
        <button
          onClick={fitAll}
          className="px-2 py-1 border border-border rounded text-xs hover:bg-muted flex items-center gap-1"
          title="Fit entire graph in view"
        >
          <Maximize2 className="w-3 h-3" />
          Fit all
        </button>
        <button
          onClick={() => setStackedMode((v) => !v)}
          disabled={!selectedNode}
          title={
            selectedNode
              ? "Pin flow_in partners to the left, flow_out to the right, of the selected node"
              : "Select a node first, then toggle this view"
          }
          className={
            "px-2 py-1 border rounded text-xs flex items-center gap-1 " +
            (stackedMode && selectedNode
              ? "border-primary bg-primary/10 text-primary"
              : "border-border hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed")
          }
        >
          In / Out view
        </button>
        <div className="ml-auto text-xs text-muted-foreground flex items-center gap-2">
          {layingOut && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
          {filtered.nodes.length} nodes · {filtered.edges.length} edges shown
        </div>
      </div>

      {data.monthly_activity && data.monthly_activity.length > 0 && (
        <DateRangeBrush
          activity={data.monthly_activity}
          from={dateFrom}
          to={dateTo}
          onChange={(f, t) => { setDateFrom(f); setDateTo(t); }}
        />
      )}

      {/* Split layout: canvas + resize handle + inspector */}
      <div
        className="bg-card border border-border rounded-lg grid gap-0 overflow-hidden relative"
        style={{
          height: "72vh",
          gridTemplateColumns: (selectedNodes.length > 0 || selectedEdge) ? `1fr 6px ${inspectorWidth}px` : "1fr 0px 0px",
          transition: "grid-template-columns 180ms ease",
        }}
      >
        <div className="relative">
          <ReactFlow
            nodes={rfNodes}
            edges={rfEdges}
            nodeTypes={NODE_TYPES}
            edgeTypes={EDGE_TYPES}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            onEdgeClick={onEdgeClick}
            onPaneClick={clearSelection}
            fitView
            minZoom={0.1}
            maxZoom={2}
            nodesDraggable
            nodesConnectable={false}
            elementsSelectable
          >
            <Background gap={16} color="#e2e8f0" />
            <Controls showInteractive={false} />
            <MiniMap
              nodeColor={(n) => {
                const id = n.id as string;
                if (id.startsWith("person:")) return MINIMAP_COLOR.person;
                if (id.startsWith("account:")) return MINIMAP_COLOR.account;
                return MINIMAP_COLOR.entity;
              }}
              pannable zoomable
            />
          </ReactFlow>
        </div>

        {(selectedNodes.length > 0 || selectedEdge) ? (
          <InspectorResizeHandle onResize={setInspectorWidth} width={inspectorWidth} />
        ) : (
          <div />
        )}

        {selectedNode && !compareNode && !selectedEdge && (
          <NodeInspector
            node={selectedNode}
            allNodes={data.nodes}
            edges={data.edges}
            onClose={clearSelection}
            caseId={caseId}
          />
        )}
        {selectedNode && compareNode && !selectedEdge && (
          <CompareInspector
            nodeA={selectedNode}
            nodeB={compareNode}
            edges={data.edges}
            onClose={clearSelection}
            onRemoveB={() => setSelectedNodes([selectedNode])}
            caseId={caseId}
          />
        )}
        {selectedEdge && (
          <EdgeInspector
            edge={selectedEdge}
            allNodes={data.nodes}
            onClose={clearSelection}
            caseId={caseId}
          />
        )}
      </div>

      <div className="bg-background border border-border rounded-lg p-3 text-xs text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="font-medium text-foreground">Legend:</span>
        <span><span style={{ color: "var(--fl-navy-800)" }}>●</span> Person</span>
        <span><span style={{ color: "#0e7490" }}>●</span> Account</span>
        <span><span style={{ color: "#475569" }}>●</span> Counterparty</span>
        <span><span style={{ color: "var(--fl-emerald-500)" }}>●</span> Salary</span>
        <span><span style={{ color: "var(--fl-navy-700)" }}>●</span> Bank</span>
        <span><span style={{ color: "#b45309" }}>●</span> Gov</span>
        <span><span style={{ color: "#94a3b8" }}>●</span> Utility</span>
        <span className="mx-1 text-border">|</span>
        <span><span style={{ color: "#dc2626" }}>→</span> flow out</span>
        <span><span style={{ color: "var(--fl-emerald-500)" }}>→</span> flow in</span>
        <span><span style={{ color: "#94a3b8" }}>→</span> ownership</span>
        <span className="ml-auto italic">click a node or edge · shift-click a second node to compare</span>
      </div>
    </div>
  );
}

// Month-bucketed bar chart with draggable start/end handles acting as a
// brushable date filter. Uses native date-input fallbacks for precise entry.
function DateRangeBrush({
  activity,
  from,
  to,
  onChange,
}: {
  activity: Array<{ month: string; count: number }>;
  from: string;
  to: string;
  onChange: (from: string, to: string) => void;
}) {
  const maxCount = Math.max(1, ...activity.map((a) => a.count));
  const months = activity.map((a) => a.month);
  const fromIdx = from ? Math.max(0, months.indexOf(from)) : 0;
  const toIdx = to ? Math.max(0, months.indexOf(to)) : months.length - 1;
  const activeFrom = fromIdx >= 0 ? fromIdx : 0;
  const activeTo = toIdx >= 0 ? toIdx : months.length - 1;

  const clear = () => onChange("", "");
  const isClamped = Boolean(from || to);

  return (
    <div className="bg-card border border-border rounded-lg p-3 flex items-center gap-3 text-xs">
      <div className="flex items-center gap-1.5 text-muted-foreground flex-shrink-0">
        <Filter className="w-3.5 h-3.5" />
        Date
      </div>
      <input
        type="month"
        value={from}
        max={to || undefined}
        onChange={(e) => onChange(e.target.value, to)}
        className="px-1.5 py-0.5 border border-border rounded bg-background text-xs tabular-nums"
        title="From month"
      />
      <span className="text-muted-foreground">→</span>
      <input
        type="month"
        value={to}
        min={from || undefined}
        onChange={(e) => onChange(from, e.target.value)}
        className="px-1.5 py-0.5 border border-border rounded bg-background text-xs tabular-nums"
        title="To month"
      />
      {isClamped && (
        <button
          onClick={clear}
          className="text-muted-foreground hover:text-foreground flex items-center gap-1"
          title="Clear date filter"
        >
          <X className="w-3 h-3" /> clear
        </button>
      )}

      {/* Inline mini bar chart. Bars outside the selected window are dimmed. */}
      <div className="flex-1 flex items-end gap-[1px] h-10 border-l border-r border-border px-1 bg-background rounded overflow-x-auto">
        {activity.map((a, i) => {
          const inRange = i >= activeFrom && i <= activeTo;
          const h = Math.max(2, (a.count / maxCount) * 34);
          return (
            <button
              key={a.month}
              onClick={() => {
                // Click a bar to snap to that month on the nearest edge:
                // if closer to the start handle, move start; else move end.
                const distL = Math.abs(i - activeFrom);
                const distR = Math.abs(i - activeTo);
                if (distL <= distR) onChange(a.month, to || months[months.length - 1]);
                else onChange(from || months[0], a.month);
              }}
              title={`${a.month} · ${a.count} txn${a.count === 1 ? "" : "s"}`}
              className="flex-shrink-0 min-w-[5px]"
              style={{
                height: `${h}px`,
                width: `max(5px, calc((100% - ${(activity.length - 1)}px) / ${activity.length}))`,
                background: inRange ? "var(--fl-navy-500)" : "var(--color-muted, #e2e8f0)",
                opacity: inRange ? 0.85 : 0.4,
                borderRadius: 1,
              }}
            />
          );
        })}
      </div>
    </div>
  );
}

function InspectorResizeHandle({
  onResize,
  width,
}: {
  onResize: (w: number) => void;
  width: number;
}) {
  const dragging = useRef(false);
  const startX = useRef(0);
  const startW = useRef(width);

  const onMouseDown = (e: React.MouseEvent) => {
    dragging.current = true;
    startX.current = e.clientX;
    startW.current = width;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      const dx = startX.current - e.clientX;
      const next = Math.min(900, Math.max(360, startW.current + dx));
      onResize(next);
    };
    const onUp = () => {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [onResize]);

  return (
    <div
      onMouseDown={onMouseDown}
      className="cursor-col-resize bg-border hover:bg-primary/40 transition-colors"
      title="Drag to resize inspector"
    />
  );
}

function NodeInspector({
  node,
  allNodes,
  edges,
  onClose,
  caseId,
}: {
  node: GraphNode;
  allNodes: GraphNode[];
  edges: GraphEdge[];
  onClose: () => void;
  caseId: string;
}) {
  const [expandedEdgeId, setExpandedEdgeId] = useState<string | null>(null);
  const patchMut = usePatchTransaction();

  const nodeById = useMemo(() => {
    const m = new Map<string, GraphNode>();
    for (const n of allNodes) m.set(n.id, n);
    return m;
  }, [allNodes]);

  const incident = edges.filter((e) => e.source === node.id || e.target === node.id);
  const flowIn = incident.filter((e) => e.kind === "flow_in" && e.target === node.id);
  const flowOut = incident.filter((e) => e.kind === "flow_out" && e.source === node.id);
  const totalIn = flowIn.reduce((s, e) => s + e.total_amount, 0);
  const totalOut = flowOut.reduce((s, e) => s + e.total_amount, 0);
  const palette = PALETTE[node.type as keyof typeof PALETTE];

  const [kind, bareId] = node.id.split(":");

  const workbenchLink = (() => {
    if (kind === "account") return `/cases/${caseId}/workbench?account=${bareId}`;
    if (kind === "person" || kind === "entity") return `/cases/${caseId}/workbench`;
    return null;
  })();

  // Flagged transactions: pull sample_txns from incident edges whose id is
  // in node.meta.flagged_txn_ids. This is best-effort (we only have samples,
  // not the full set), so we show a "see all in Workbench" link for the rest.
  const flaggedIds: string[] = Array.isArray(node.meta?.flagged_txn_ids)
    ? node.meta.flagged_txn_ids
    : [];
  const flaggedIdSet = new Set(flaggedIds);
  const flaggedSampleTxns: GraphEdgeSample[] = useMemo(() => {
    if (flaggedIdSet.size === 0) return [];
    const seen = new Set<string>();
    const out: GraphEdgeSample[] = [];
    for (const e of incident) {
      for (const t of e.sample_txns) {
        if (flaggedIdSet.has(t.id) && !seen.has(t.id)) {
          seen.add(t.id);
          out.push(t);
        }
      }
    }
    return out.sort((a, b) => (a.txn_date < b.txn_date ? 1 : -1));
  }, [incident, flaggedIds.join(",")]);

  const unflagOne = (txnId: string) => {
    patchMut.mutate({ id: txnId, patch: { review_status: "unreviewed" } });
  };
  const unflagAll = () => {
    for (const id of flaggedIds) {
      patchMut.mutate({ id, patch: { review_status: "unreviewed" } });
    }
  };

  // Edge-row click-through: for flow edges, deep-link to Workbench filtered
  // to the account side (whichever end is an account).
  const edgeWorkbenchLink = (e: GraphEdge): string => {
    const [sk, sb] = e.source.split(":");
    const [tk, tb] = e.target.split(":");
    if (sk === "account") return `/cases/${caseId}/workbench?account=${sb}`;
    if (tk === "account") return `/cases/${caseId}/workbench?account=${tb}`;
    return `/cases/${caseId}/workbench`;
  };

  // Sort incident edges: flows by total_amount desc, owns first for persons.
  const sortedIncident = [...incident].sort((a, b) => {
    if (a.kind === "owns" && b.kind !== "owns") return -1;
    if (b.kind === "owns" && a.kind !== "owns") return 1;
    return b.total_amount - a.total_amount;
  });

  // Flatten all sample txns across incident edges (for the Transactions tab).
  const allSampleTxns: Array<GraphEdgeSample & { edgeId: string; otherLabel: string }> = useMemo(() => {
    const seen = new Set<string>();
    const out: Array<GraphEdgeSample & { edgeId: string; otherLabel: string }> = [];
    for (const e of incident) {
      if (e.kind === "owns") continue;
      const otherId = e.source === node.id ? e.target : e.source;
      const otherLabel = nodeById.get(otherId)?.label ?? otherId;
      for (const t of e.sample_txns) {
        if (seen.has(t.id)) continue;
        seen.add(t.id);
        out.push({ ...t, edgeId: e.id, otherLabel });
      }
    }
    return out.sort((a, b) => (a.txn_date < b.txn_date ? 1 : -1));
  }, [incident, nodeById, node.id]);

  const totalIncidentTxns = incident
    .filter((e) => e.kind !== "owns")
    .reduce((s, e) => s + e.txn_count, 0);

  // Pattern hits: { name -> count } from backend.
  const patternHits: Record<string, number> =
    node.meta?.pattern_hits && typeof node.meta.pattern_hits === "object"
      ? node.meta.pattern_hits
      : {};
  const patternHitList = Object.entries(patternHits).sort((a, b) => b[1] - a[1]);

  // Related nodes: group the other-end of each incident flow edge by type.
  const relatedGrouped = useMemo(() => {
    const out: Record<string, Array<{ node: GraphNode; edge: GraphEdge; isOut: boolean }>> = {
      person: [], account: [], entity: [],
    };
    const seen = new Set<string>();
    for (const e of incident) {
      const otherId = e.source === node.id ? e.target : e.source;
      if (seen.has(otherId)) continue;
      seen.add(otherId);
      const other = nodeById.get(otherId);
      if (!other) continue;
      out[other.type]?.push({ node: other, edge: e, isOut: e.source === node.id });
    }
    return out;
  }, [incident, nodeById, node.id]);

  const [tab, setTab] = useState<"overview" | "flows" | "transactions" | "patterns" | "related">("overview");

  const tabs: Array<{ id: typeof tab; label: string; count?: number }> = [
    { id: "overview", label: "Overview" },
    { id: "flows", label: "Flows", count: sortedIncident.filter((e) => e.kind !== "owns").length },
    { id: "transactions", label: "Transactions", count: allSampleTxns.length },
    { id: "patterns", label: "Patterns", count: patternHitList.length },
    { id: "related", label: "Related", count: relatedGrouped.account.length + relatedGrouped.entity.length + relatedGrouped.person.length },
  ];

  return (
    <div className="border-l border-border bg-card flex flex-col min-w-0">
      <div className="px-4 py-3 border-b border-border flex items-center justify-between">
        <div className="min-w-0">
          <div className="text-xs uppercase tracking-wider" style={{ color: palette.bg }}>
            {node.type}
          </div>
          <div className="font-semibold text-foreground truncate" title={node.label}>{node.label}</div>
        </div>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground flex-shrink-0">
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Tab strip */}
      <div className="flex border-b border-border bg-background/50 text-xs overflow-x-auto flex-shrink-0">
        {tabs.map((t) => {
          const active = t.id === tab;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={
                "px-3 py-2 border-b-2 flex items-center gap-1.5 whitespace-nowrap " +
                (active
                  ? "border-primary text-foreground font-medium"
                  : "border-transparent text-muted-foreground hover:text-foreground")
              }
            >
              {t.label}
              {typeof t.count === "number" && t.count > 0 && (
                <span className={
                  "text-[10px] px-1 py-0 rounded tabular-nums " +
                  (active ? "bg-primary/20 text-primary" : "bg-muted text-muted-foreground")
                }>
                  {t.count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4 text-sm">
        {tab === "overview" && (<>
        <div className="flex items-center gap-6">
          <div>
            <div className="text-xs uppercase tracking-wider text-muted-foreground mb-0.5">ID</div>
            <div className="font-mono text-foreground text-xs">{bareId}</div>
          </div>
          {node.type === "account" && node.meta.bank && (
            <div>
              <div className="text-xs uppercase tracking-wider text-muted-foreground mb-0.5">Bank</div>
              <div className="text-foreground">{node.meta.bank} · {node.meta.type}</div>
            </div>
          )}
          {node.type === "account" && node.meta.holder_name && node.meta.holder_name !== "Unknown" && (
            <div>
              <div className="text-xs uppercase tracking-wider text-muted-foreground mb-0.5">Holder</div>
              <div className="text-foreground">{node.meta.holder_name}</div>
            </div>
          )}
        </div>

        {node.type === "entity" && Array.isArray(node.meta.aliases) && node.meta.aliases.length > 0 && (
          <div>
            <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Aliases</div>
            <div className="flex flex-wrap gap-1">
              {node.meta.aliases.slice(0, 10).map((a: string) => (
                <span key={a} className="text-xs px-1.5 py-0.5 bg-background border border-border rounded text-foreground">{a}</span>
              ))}
              {node.meta.aliases.length > 10 && <span className="text-xs text-muted-foreground">+{node.meta.aliases.length - 10}</span>}
            </div>
          </div>
        )}

        {flaggedIds.length > 0 && (
          <div className="border border-[color:var(--fl-ruby-500)]/40 bg-[color:var(--fl-ruby-500)]/10 rounded p-2.5 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-[color:var(--fl-ruby-500)]">
                <Flag className="w-4 h-4" />
                <span className="font-semibold text-sm">
                  {flaggedIds.length} flagged transaction{flaggedIds.length === 1 ? "" : "s"}
                </span>
              </div>
              <button
                onClick={unflagAll}
                disabled={patchMut.isPending}
                className="text-[11px] px-2 py-1 border border-[color:var(--fl-ruby-500)]/40 text-[color:var(--fl-ruby-500)] rounded hover:bg-[color:var(--fl-ruby-500)]/20 disabled:opacity-50"
                title="Clear the flag on all flagged transactions for this node"
              >
                Unflag all
              </button>
            </div>
            {flaggedSampleTxns.length > 0 ? (
              <div className="space-y-1 max-h-60 overflow-y-auto pr-1">
                {flaggedSampleTxns.map((t) => (
                  <div key={t.id} className="bg-background border border-border rounded px-2 py-1.5 text-[11px] flex items-center gap-2">
                    <span className="text-muted-foreground font-mono w-14 flex-shrink-0">
                      {new Date(t.txn_date).toLocaleDateString("en-GB", { day: "2-digit", month: "2-digit", year: "2-digit" })}
                    </span>
                    <span className={`tabular-nums w-20 text-right flex-shrink-0 ${t.direction === "Dr" ? "text-destructive" : "text-[color:var(--fl-emerald-500)]"}`}>
                      {t.direction === "Dr" ? "−" : "+"}{formatINR(t.amount)}
                    </span>
                    <span className="text-muted-foreground truncate flex-1" title={t.raw_description}>
                      {t.raw_description}
                    </span>
                    <button
                      onClick={() => unflagOne(t.id)}
                      disabled={patchMut.isPending}
                      className="text-[10px] px-1.5 py-0.5 border border-border rounded hover:bg-muted flex-shrink-0 disabled:opacity-50"
                      title="Clear the flag on this transaction"
                    >
                      Unflag
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-[11px] text-muted-foreground italic">
                Flagged txns are not in the visible edge sample — open in Workbench to review them.
              </div>
            )}
            {flaggedIds.length > flaggedSampleTxns.length && flaggedSampleTxns.length > 0 && (
              <div className="text-[11px] text-muted-foreground italic">
                +{flaggedIds.length - flaggedSampleTxns.length} more flagged — open in Workbench to see all.
              </div>
            )}
          </div>
        )}

        {(flowIn.length > 0 || flowOut.length > 0) && (
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-background border border-border rounded p-2">
              <div className="text-xs text-muted-foreground">Flow in</div>
              <div className="text-base font-semibold text-[color:var(--fl-emerald-500)] tabular-nums">{formatINR(totalIn)}</div>
              <div className="text-xs text-muted-foreground">{flowIn.reduce((s, e) => s + e.txn_count, 0)} txns across {flowIn.length} source{flowIn.length !== 1 ? "s" : ""}</div>
            </div>
            <div className="bg-background border border-border rounded p-2">
              <div className="text-xs text-muted-foreground">Flow out</div>
              <div className="text-base font-semibold text-destructive tabular-nums">{formatINR(totalOut)}</div>
              <div className="text-xs text-muted-foreground">{flowOut.reduce((s, e) => s + e.txn_count, 0)} txns across {flowOut.length} target{flowOut.length !== 1 ? "s" : ""}</div>
            </div>
          </div>
        )}
        </>)}

        {tab === "flows" && sortedIncident.length > 0 && (
          <div>
            <div className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
              Connected edges ({sortedIncident.length})
            </div>
            <div className="space-y-1.5 max-h-[420px] overflow-y-auto pr-1">
              {sortedIncident.map((e) => {
                const otherId = e.source === node.id ? e.target : e.source;
                const otherNode = nodeById.get(otherId);
                const otherLabel = otherNode?.label ?? otherId;
                const isExpanded = expandedEdgeId === e.id;
                const isOut = e.source === node.id;
                const directionLabel =
                  e.kind === "owns" ? "owns"
                  : isOut ? "→ to"
                  : "← from";
                const directionColor =
                  e.kind === "owns" ? "text-muted-foreground"
                  : e.kind === "flow_out" ? "text-destructive"
                  : "text-[color:var(--fl-emerald-500)]";
                return (
                  <div key={e.id} className="border border-border rounded bg-background">
                    <button
                      onClick={() => setExpandedEdgeId(isExpanded ? null : e.id)}
                      className="w-full px-2.5 py-2 text-xs flex items-center gap-2 hover:bg-muted/50 rounded-t"
                    >
                      {e.kind !== "owns" ? (
                        isExpanded ? <ChevronDown className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
                                   : <ChevronRight className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
                      ) : (
                        <span className="w-3.5 flex-shrink-0" />
                      )}
                      <span className={`font-medium ${directionColor} flex-shrink-0`}>{directionLabel}</span>
                      <span className="text-foreground truncate text-left flex-1" title={otherLabel}>
                        {otherLabel}
                      </span>
                      {e.kind !== "owns" && (
                        <span className="text-muted-foreground tabular-nums flex-shrink-0">
                          {e.txn_count}× · {formatINR(e.total_amount)}
                        </span>
                      )}
                    </button>
                    {isExpanded && e.sample_txns.length > 0 && (
                      <div className="border-t border-border px-2 py-1.5 space-y-1 bg-card">
                        {e.sample_txns.map((t) => (
                          <div key={t.id} className="text-[11px] flex items-center gap-2">
                            <span className="text-muted-foreground font-mono w-16 flex-shrink-0">
                              {new Date(t.txn_date).toLocaleDateString("en-GB", { day: "2-digit", month: "2-digit", year: "2-digit" })}
                            </span>
                            <span className={`tabular-nums w-20 text-right flex-shrink-0 ${t.direction === "Dr" ? "text-destructive" : "text-[color:var(--fl-emerald-500)]"}`}>
                              {t.direction === "Dr" ? "−" : "+"}{formatINR(t.amount)}
                            </span>
                            <span className="text-muted-foreground truncate flex-1" title={t.raw_description}>
                              {t.raw_description}
                            </span>
                          </div>
                        ))}
                        {e.kind !== "owns" && (
                          <a
                            href={edgeWorkbenchLink(e)}
                            className="inline-flex items-center gap-1 text-[11px] text-primary hover:text-primary/80 pt-1"
                          >
                            <ExternalLink className="w-3 h-3" />
                            Open in Workbench
                            {e.txn_count > e.sample_txns.length
                              ? ` (${e.txn_count - e.sample_txns.length} more)`
                              : ""}
                          </a>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {tab === "flows" && sortedIncident.length === 0 && (
          <div className="text-xs text-muted-foreground italic">No connected edges.</div>
        )}

        {tab === "transactions" && (
          <div>
            <div className="text-xs uppercase tracking-wider text-muted-foreground mb-2 flex items-center justify-between">
              <span>Transactions ({allSampleTxns.length}{totalIncidentTxns > allSampleTxns.length ? ` of ${totalIncidentTxns}` : ""})</span>
              {workbenchLink && (
                <a href={workbenchLink} className="text-primary hover:text-primary/80 inline-flex items-center gap-1 normal-case tracking-normal">
                  <ExternalLink className="w-3 h-3" /> Open all
                </a>
              )}
            </div>
            {allSampleTxns.length === 0 ? (
              <div className="text-xs text-muted-foreground italic">No sample transactions available.</div>
            ) : (
              <div className="space-y-1">
                {allSampleTxns.map((t) => (
                  <div key={t.id} className="bg-background border border-border rounded px-2 py-1.5 text-[11px] flex items-center gap-2">
                    <span className="text-muted-foreground font-mono w-14 flex-shrink-0">
                      {new Date(t.txn_date).toLocaleDateString("en-GB", { day: "2-digit", month: "2-digit", year: "2-digit" })}
                    </span>
                    <span className={`tabular-nums w-20 text-right flex-shrink-0 ${t.direction === "Dr" ? "text-destructive" : "text-[color:var(--fl-emerald-500)]"}`}>
                      {t.direction === "Dr" ? "−" : "+"}{formatINR(t.amount)}
                    </span>
                    <span className="text-muted-foreground truncate flex-1" title={`${t.otherLabel} — ${t.raw_description}`}>
                      {t.otherLabel} · <span className="opacity-70">{t.raw_description}</span>
                    </span>
                  </div>
                ))}
              </div>
            )}
            {totalIncidentTxns > allSampleTxns.length && allSampleTxns.length > 0 && (
              <div className="text-[11px] text-muted-foreground italic pt-2">
                Showing samples — {totalIncidentTxns - allSampleTxns.length} more in Workbench.
              </div>
            )}
          </div>
        )}

        {tab === "patterns" && (
          <div>
            <div className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
              Pattern hits ({patternHitList.length})
            </div>
            {patternHitList.length === 0 ? (
              <div className="text-xs text-muted-foreground italic">
                No forensic pattern hits on this node.
              </div>
            ) : (
              <div className="space-y-1.5">
                {patternHitList.map(([name, count]) => (
                  <div key={name} className="bg-background border border-border rounded px-2.5 py-2 flex items-center gap-2">
                    <Flag className="w-3.5 h-3.5 text-[color:var(--fl-ruby-500)] flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium text-foreground">{PATTERN_LABELS[name] ?? name}</div>
                      <div className="text-[11px] text-muted-foreground">{name.toLowerCase().replaceAll("_", " ")}</div>
                    </div>
                    <span className="text-xs tabular-nums text-muted-foreground flex-shrink-0">
                      {count} txn{count === 1 ? "" : "s"}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {tab === "related" && (
          <div className="space-y-3">
            {(["account", "entity", "person"] as const).map((k) => {
              const group = relatedGrouped[k];
              if (!group || group.length === 0) return null;
              const groupLabel = k === "account" ? "Accounts" : k === "entity" ? "Entities" : "Persons";
              return (
                <div key={k}>
                  <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1.5">
                    {groupLabel} ({group.length})
                  </div>
                  <div className="space-y-1">
                    {group
                      .sort((a, b) => b.edge.total_amount - a.edge.total_amount)
                      .map(({ node: n, edge: e, isOut }) => (
                        <div key={n.id} className="bg-background border border-border rounded px-2.5 py-1.5 text-xs flex items-center gap-2">
                          <span className={
                            e.kind === "owns" ? "text-muted-foreground"
                            : e.kind === "flow_out" || isOut ? "text-destructive"
                            : "text-[color:var(--fl-emerald-500)]"
                          }>
                            {e.kind === "owns" ? "↔" : isOut ? "→" : "←"}
                          </span>
                          <span className="text-foreground truncate flex-1" title={n.label}>{n.label}</span>
                          {e.kind !== "owns" && (
                            <span className="text-muted-foreground tabular-nums flex-shrink-0">
                              {e.txn_count}× · {formatINR(e.total_amount)}
                            </span>
                          )}
                        </div>
                      ))}
                  </div>
                </div>
              );
            })}
            {relatedGrouped.account.length === 0 &&
              relatedGrouped.entity.length === 0 &&
              relatedGrouped.person.length === 0 && (
                <div className="text-xs text-muted-foreground italic">No connected nodes.</div>
              )}
          </div>
        )}
      </div>

      {workbenchLink && (
        <div className="border-t border-border px-4 py-2">
          <a
            href={workbenchLink}
            className="text-xs text-primary hover:text-primary/80 flex items-center gap-1"
          >
            <ExternalLink className="w-3 h-3" />
            Open in Workbench
          </a>
        </div>
      )}
    </div>
  );
}

const PATTERN_LABELS: Record<string, string> = {
  STRUCTURING_SUSPECTED: "Structuring suspected",
  VELOCITY_SPIKE: "Velocity spike",
  ROUND_AMOUNT_CLUSTER: "Round-amount cluster",
  FUND_THROUGH_FLOW: "Fund-through flow",
  DORMANT_THEN_ACTIVE: "Dormant → active",
  SAME_DAY_ROUND_TRIP: "Same-day round trip",
};

function EdgeInspector({
  edge,
  allNodes,
  onClose,
  caseId,
}: {
  edge: GraphEdge;
  allNodes: GraphNode[];
  onClose: () => void;
  caseId: string;
}) {
  const nodeById = useMemo(() => {
    const m = new Map<string, GraphNode>();
    for (const n of allNodes) m.set(n.id, n);
    return m;
  }, [allNodes]);

  const src = nodeById.get(edge.source);
  const tgt = nodeById.get(edge.target);

  const kindLabel =
    edge.kind === "flow_out" ? "Flow out (debit)"
    : edge.kind === "flow_in" ? "Flow in (credit)"
    : "Ownership";
  const kindColor =
    edge.kind === "flow_out" ? "#dc2626"
    : edge.kind === "flow_in" ? "var(--fl-emerald-500)"
    : "#94a3b8";

  const dates = edge.sample_txns
    .map((t) => t.txn_date)
    .filter(Boolean)
    .sort();
  const minDate = dates[0];
  const maxDate = dates[dates.length - 1];

  // Best workbench deep-link: whichever end is an account.
  const [srcKind, srcBare] = edge.source.split(":");
  const [tgtKind, tgtBare] = edge.target.split(":");
  const accountBareId =
    srcKind === "account" ? srcBare :
    tgtKind === "account" ? tgtBare : null;
  const workbenchLink = accountBareId
    ? `/cases/${caseId}/workbench?account=${accountBareId}`
    : `/cases/${caseId}/workbench`;

  return (
    <div className="border-l border-border bg-card flex flex-col min-w-0">
      <div className="px-4 py-3 border-b border-border flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="text-xs uppercase tracking-wider" style={{ color: kindColor }}>
            {kindLabel}
          </div>
          <div className="font-semibold text-foreground text-sm leading-tight mt-1 flex items-center gap-1.5 flex-wrap">
            <span className="truncate" title={src?.label}>{src?.label ?? edge.source}</span>
            <span className="text-muted-foreground">→</span>
            <span className="truncate" title={tgt?.label}>{tgt?.label ?? edge.target}</span>
          </div>
        </div>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground flex-shrink-0">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4 text-sm">
        {edge.kind !== "owns" && (
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-background border border-border rounded p-2">
              <div className="text-xs text-muted-foreground">Total</div>
              <div className="text-base font-semibold tabular-nums" style={{ color: kindColor }}>
                {formatINR(edge.total_amount)}
              </div>
              <div className="text-xs text-muted-foreground">
                {edge.txn_count} txn{edge.txn_count !== 1 ? "s" : ""}
              </div>
            </div>
            {minDate && maxDate && (
              <div className="bg-background border border-border rounded p-2">
                <div className="text-xs text-muted-foreground">Range</div>
                <div className="text-xs font-semibold text-foreground tabular-nums">
                  {new Date(minDate).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "2-digit" })}
                  {" → "}
                  {new Date(maxDate).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "2-digit" })}
                </div>
                <div className="text-xs text-muted-foreground">of visible sample</div>
              </div>
            )}
          </div>
        )}

        <div>
          <div className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
            Transactions ({edge.sample_txns.length}
            {edge.txn_count > edge.sample_txns.length ? ` of ${edge.txn_count}` : ""})
          </div>
          <div className="space-y-1">
            {edge.sample_txns.map((t) => (
              <div key={t.id} className="border border-border rounded bg-background px-2 py-1.5 text-[11px] flex items-center gap-2">
                <span className="text-muted-foreground font-mono w-14 flex-shrink-0">
                  {new Date(t.txn_date).toLocaleDateString("en-GB", { day: "2-digit", month: "2-digit", year: "2-digit" })}
                </span>
                <span className={`tabular-nums w-20 text-right flex-shrink-0 ${t.direction === "Dr" ? "text-destructive" : "text-[color:var(--fl-emerald-500)]"}`}>
                  {t.direction === "Dr" ? "−" : "+"}{formatINR(t.amount)}
                </span>
                <span className="text-muted-foreground truncate" title={t.raw_description}>
                  {t.raw_description}
                </span>
              </div>
            ))}
            {edge.sample_txns.length === 0 && (
              <div className="text-[11px] text-muted-foreground italic">
                No sample transactions available on this edge.
              </div>
            )}
            {edge.txn_count > edge.sample_txns.length && (
              <div className="text-[11px] text-muted-foreground italic pt-1">
                +{edge.txn_count - edge.sample_txns.length} more — open in Workbench to see all
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="border-t border-border px-4 py-2">
        <a
          href={workbenchLink}
          className="text-xs text-primary hover:text-primary/80 flex items-center gap-1"
        >
          <ExternalLink className="w-3 h-3" />
          Open in Workbench
        </a>
      </div>
    </div>
  );
}

// Side-by-side stats for two selected nodes. Highlights common neighbours
// and lets the investigator scan differences quickly.
function CompareInspector({
  nodeA,
  nodeB,
  edges,
  onClose,
  onRemoveB,
  caseId,
}: {
  nodeA: GraphNode;
  nodeB: GraphNode;
  edges: GraphEdge[];
  onClose: () => void;
  onRemoveB: () => void;
  caseId: string;
}) {
  const statsFor = (n: GraphNode) => {
    const incident = edges.filter((e) => e.source === n.id || e.target === n.id);
    const flowIn = incident.filter((e) => e.kind === "flow_in" && e.target === n.id);
    const flowOut = incident.filter((e) => e.kind === "flow_out" && e.source === n.id);
    const totalIn = flowIn.reduce((s, e) => s + e.total_amount, 0);
    const totalOut = flowOut.reduce((s, e) => s + e.total_amount, 0);
    const txnCount = incident
      .filter((e) => e.kind !== "owns")
      .reduce((s, e) => s + e.txn_count, 0);
    const neighbours = new Set<string>();
    for (const e of incident) {
      const other = e.source === n.id ? e.target : e.source;
      neighbours.add(other);
    }
    return {
      incident, flowIn, flowOut, totalIn, totalOut, txnCount,
      neighbours,
      flagged: Boolean(n.meta?.flagged),
      flaggedCount: Array.isArray(n.meta?.flagged_txn_ids) ? n.meta.flagged_txn_ids.length : 0,
    };
  };

  const a = statsFor(nodeA);
  const b = statsFor(nodeB);

  const sharedNeighbourIds: string[] = [];
  for (const id of a.neighbours) if (b.neighbours.has(id)) sharedNeighbourIds.push(id);

  const Card = ({ n, s, onRemove }: { n: GraphNode; s: ReturnType<typeof statsFor>; onRemove?: () => void }) => (
    <div className="bg-background border border-border rounded p-3 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{n.type}</div>
          <div className="font-semibold text-sm truncate" title={n.label}>{n.label}</div>
        </div>
        {onRemove && (
          <button onClick={onRemove} className="text-muted-foreground hover:text-foreground flex-shrink-0" title="Remove from compare">
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
      <div className="grid grid-cols-2 gap-1.5 text-xs">
        <div>
          <div className="text-muted-foreground">Flow in</div>
          <div className="font-semibold text-[color:var(--fl-emerald-500)] tabular-nums">{formatINR(s.totalIn)}</div>
        </div>
        <div>
          <div className="text-muted-foreground">Flow out</div>
          <div className="font-semibold text-destructive tabular-nums">{formatINR(s.totalOut)}</div>
        </div>
        <div>
          <div className="text-muted-foreground">Txns</div>
          <div className="font-semibold tabular-nums">{s.txnCount}</div>
        </div>
        <div>
          <div className="text-muted-foreground">Neighbours</div>
          <div className="font-semibold tabular-nums">{s.neighbours.size}</div>
        </div>
      </div>
      {s.flagged && (
        <div className="text-[11px] text-[color:var(--fl-ruby-500)] flex items-center gap-1">
          <Flag className="w-3 h-3" />
          {s.flaggedCount} flagged txn{s.flaggedCount === 1 ? "" : "s"}
        </div>
      )}
    </div>
  );

  return (
    <div className="border-l border-border bg-card flex flex-col min-w-0">
      <div className="px-4 py-3 border-b border-border flex items-center justify-between">
        <div className="min-w-0">
          <div className="text-xs uppercase tracking-wider text-muted-foreground">Comparing</div>
          <div className="font-semibold text-foreground text-sm">2 nodes</div>
        </div>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground flex-shrink-0">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 text-sm">
        <div className="grid grid-cols-2 gap-2">
          <Card n={nodeA} s={a} />
          <Card n={nodeB} s={b} onRemove={onRemoveB} />
        </div>

        <div className="bg-background border border-border rounded p-2.5">
          <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1.5">
            Shared neighbours ({sharedNeighbourIds.length})
          </div>
          {sharedNeighbourIds.length === 0 ? (
            <div className="text-xs text-muted-foreground italic">
              These two nodes have no common neighbours in the visible graph.
            </div>
          ) : (
            <div className="space-y-1">
              {sharedNeighbourIds.slice(0, 30).map((id) => (
                <div key={id} className="text-xs text-foreground truncate" title={id}>
                  · {id.split(":").slice(1).join(":")}
                </div>
              ))}
              {sharedNeighbourIds.length > 30 && (
                <div className="text-[11px] text-muted-foreground italic">
                  +{sharedNeighbourIds.length - 30} more
                </div>
              )}
            </div>
          )}
        </div>

        <div className="bg-background border border-border rounded p-2.5">
          <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1.5">Deltas</div>
          <div className="grid grid-cols-[1fr_auto_auto] gap-x-3 gap-y-1 text-xs tabular-nums">
            <div className="text-muted-foreground">Flow in</div>
            <div className="text-right">{formatINR(a.totalIn)} vs {formatINR(b.totalIn)}</div>
            <div className={a.totalIn >= b.totalIn ? "text-[color:var(--fl-emerald-500)]" : "text-destructive"}>
              {a.totalIn >= b.totalIn ? "A +" : "B +"}{formatINR(Math.abs(a.totalIn - b.totalIn))}
            </div>
            <div className="text-muted-foreground">Flow out</div>
            <div className="text-right">{formatINR(a.totalOut)} vs {formatINR(b.totalOut)}</div>
            <div className={a.totalOut >= b.totalOut ? "text-destructive" : "text-[color:var(--fl-emerald-500)]"}>
              {a.totalOut >= b.totalOut ? "A +" : "B +"}{formatINR(Math.abs(a.totalOut - b.totalOut))}
            </div>
            <div className="text-muted-foreground">Txns</div>
            <div className="text-right">{a.txnCount} vs {b.txnCount}</div>
            <div className="text-foreground">{a.txnCount >= b.txnCount ? "A +" : "B +"}{Math.abs(a.txnCount - b.txnCount)}</div>
          </div>
        </div>

        <div className="text-[11px] text-muted-foreground italic">
          Tip: shift-click another node to swap B. Click the X on B to drop it and return to single view.
        </div>
      </div>

      <div className="border-t border-border px-4 py-2">
        <a
          href={`/cases/${caseId}/workbench`}
          className="text-xs text-primary hover:text-primary/80 flex items-center gap-1"
        >
          <ExternalLink className="w-3 h-3" />
          Open in Workbench
        </a>
      </div>
    </div>
  );
}
