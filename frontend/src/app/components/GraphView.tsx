import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeMouseHandler,
  type EdgeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import ELK from "elkjs/lib/elk.bundled.js";
import { Filter, Loader2, X, ExternalLink, Search, ChevronDown, ChevronRight } from "lucide-react";
import { useCaseGraph } from "../lib/queries";
import type { GraphNode, GraphEdge } from "../lib/api";
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
  const { data, isLoading, error } = useCaseGraph(caseId);

  const [showPersons, setShowPersons] = useState(true);
  const [showAccounts, setShowAccounts] = useState(true);
  const [showEntities, setShowEntities] = useState(true);
  const [minAmount, setMinAmount] = useState(50_000);
  const [hideOrphans, setHideOrphans] = useState(true);
  const [layout, setLayout] = useState<LayoutMode>("layered");
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);
  const [layingOut, setLayingOut] = useState(false);
  const [search, setSearch] = useState("");

  const [rfNodes, setRfNodes, onNodesChange] = useNodesState<Node>([]);
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState<Edge>([]);

  const filtered = useMemo(() => {
    if (!data) return { nodes: [] as GraphNode[], edges: [] as GraphEdge[] };
    let nodes = data.nodes.filter((n) => {
      if (n.type === "person") return showPersons;
      if (n.type === "account") return showAccounts;
      if (n.type === "entity") return showEntities;
      return true;
    });
    let nodeIds = new Set(nodes.map((n) => n.id));
    const edges = data.edges.filter((e) => {
      if (!nodeIds.has(e.source) || !nodeIds.has(e.target)) return false;
      if (e.kind === "owns") return true;
      return e.total_amount >= minAmount;
    });

    // Hide orphans: any node with no incident edges after the amount filter.
    // Persons are always kept if their accounts are visible — otherwise the
    // case's root disappears even when the money flows out of its accounts.
    if (hideOrphans) {
      const incident = new Set<string>();
      for (const e of edges) { incident.add(e.source); incident.add(e.target); }
      nodes = nodes.filter((n) => incident.has(n.id));
      nodeIds = new Set(nodes.map((n) => n.id));
    }

    return { nodes, edges };
  }, [data, showPersons, showAccounts, showEntities, minAmount, hideOrphans]);

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
  // just that edge + its two endpoints; a node click focuses the node and all
  // its incident edges (plus the far-side nodes so the connections read).
  const focus: FocusSet = useMemo(() => {
    if (selectedEdge) {
      return {
        nodes: new Set<string>([selectedEdge.source, selectedEdge.target]),
        edges: new Set<string>([selectedEdge.id]),
      };
    }
    if (selectedNode && data) {
      const nodes = new Set<string>([selectedNode.id]);
      const edges = new Set<string>();
      for (const e of data.edges) {
        if (e.source === selectedNode.id || e.target === selectedNode.id) {
          edges.add(e.id);
          nodes.add(e.source);
          nodes.add(e.target);
        }
      }
      return { nodes, edges };
    }
    return null;
  }, [selectedNode, selectedEdge, data]);

  // (Re-)compute ELK layout whenever filtered graph or mode changes.
  useEffect(() => {
    if (!filtered.nodes.length) {
      setRfNodes([]);
      setRfEdges([]);
      return;
    }
    let cancelled = false;
    setLayingOut(true);
    computeElkLayout(filtered.nodes, filtered.edges, layout)
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
              dim,
            },
            draggable: true,
          };
        });
        setRfNodes(next);
        setRfEdges(buildEdges(filtered.edges, focus, matchSet, selectedEdge?.id ?? null));
      })
      .catch((e) => console.error("ELK layout failed:", e))
      .finally(() => { if (!cancelled) setLayingOut(false); });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtered, layout]);

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

  const onNodeClick: NodeMouseHandler = useCallback((_e, node) => {
    const gn = data?.nodes.find((n) => n.id === node.id);
    if (gn) {
      setSelectedNode(gn);
      setSelectedEdge(null);
    }
  }, [data]);

  const onEdgeClick: EdgeMouseHandler = useCallback((_e, edge) => {
    const ge = data?.edges.find((x) => x.id === edge.id);
    if (ge) {
      setSelectedEdge(ge);
      setSelectedNode(null);
    }
  }, [data]);

  const clearSelection = useCallback(() => {
    setSelectedNode(null);
    setSelectedEdge(null);
  }, []);

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
            placeholder="Find entity / account…"
            className="pl-8 pr-6 py-1.5 border border-border rounded text-sm w-56 focus:outline-none focus:ring-1 focus:ring-primary"
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
        </label>
        <div className="ml-auto text-xs text-muted-foreground flex items-center gap-2">
          {layingOut && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
          {filtered.nodes.length} nodes · {filtered.edges.length} edges shown
        </div>
      </div>

      {/* Split layout: canvas + inspector */}
      <div
        className="bg-card border border-border rounded-lg grid gap-0 overflow-hidden"
        style={{
          height: "72vh",
          gridTemplateColumns: (selectedNode || selectedEdge) ? "1fr 520px" : "1fr 0px",
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

        {selectedNode && !selectedEdge && (
          <NodeInspector
            node={selectedNode}
            allNodes={data.nodes}
            edges={data.edges}
            onClose={clearSelection}
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
        <span className="ml-auto italic">click a node or an edge to inspect</span>
      </div>
    </div>
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

  // Sort incident edges: flows by total_amount desc, owns first for persons.
  const sortedIncident = [...incident].sort((a, b) => {
    if (a.kind === "owns" && b.kind !== "owns") return -1;
    if (b.kind === "owns" && a.kind !== "owns") return 1;
    return b.total_amount - a.total_amount;
  });

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

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4 text-sm">
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

        {sortedIncident.length > 0 && (
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
                            <span className="text-muted-foreground truncate" title={t.raw_description}>
                              {t.raw_description}
                            </span>
                          </div>
                        ))}
                        {e.txn_count > e.sample_txns.length && (
                          <div className="text-[11px] text-muted-foreground italic">
                            +{e.txn_count - e.sample_txns.length} more — open in Workbench to see all
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
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
