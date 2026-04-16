import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
  type Node,
  type Edge,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import ELK from "elkjs/lib/elk.bundled.js";
import { Filter, Loader2, X, ExternalLink } from "lucide-react";
import { useCaseGraph } from "../lib/queries";
import type { GraphNode, GraphEdge } from "../lib/api";

interface GraphViewProps {
  caseId: string;
}

const elk = new ELK();

const PALETTE = {
  person:  { bg: "#1e3a8a", text: "#fff", border: "#1e40af" },
  account: { bg: "#0891b2", text: "#fff", border: "#0e7490" },
  entity:  { bg: "#f1f5f9", text: "#1e293b", border: "#cbd5e1" },
};

const NODE_W = 240;
const NODE_H = 52;

type LayoutMode = "layered" | "force" | "radial";

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
  force: {
    "elk.algorithm": "force",
    "elk.force.iterations": "300",
    "elk.spacing.nodeNode": "80",
    "elk.force.repulsivePower": "1",
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

function nodeStyle(type: string): React.CSSProperties {
  const palette = PALETTE[type as keyof typeof PALETTE] ?? PALETTE.entity;
  return {
    background: palette.bg,
    color: palette.text,
    border: `1px solid ${palette.border}`,
    borderRadius: 6,
    width: NODE_W,
    height: NODE_H,
    fontSize: 12,
  };
}

async function computeElkLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  mode: LayoutMode,
): Promise<Map<string, { x: number; y: number }>> {
  const elkGraph = {
    id: "root",
    layoutOptions: ELK_ALGORITHMS[mode],
    children: nodes.map((n) => ({ id: n.id, width: NODE_W, height: NODE_H })),
    edges: edges.map((e) => ({ id: e.id, sources: [e.source], targets: [e.target] })),
  };
  const layout = await elk.layout(elkGraph as any);
  const positions = new Map<string, { x: number; y: number }>();
  for (const child of layout.children ?? []) {
    positions.set(child.id as string, { x: (child as any).x ?? 0, y: (child as any).y ?? 0 });
  }
  return positions;
}

function buildEdges(edges: GraphEdge[], highlightId?: string): Edge[] {
  return edges.map((e) => {
    const isFlow = e.kind !== "owns";
    const strokeWidth = isFlow ? Math.min(6, 1 + Math.log10(Math.max(1, e.total_amount) / 1000)) : 1;
    const color =
      e.kind === "flow_out" ? "#dc2626"
      : e.kind === "flow_in" ? "#16a34a"
      : "#94a3b8";
    const dim = highlightId && e.source !== highlightId && e.target !== highlightId;
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      label: isFlow ? `${e.txn_count}× ${formatINR(e.total_amount)}` : undefined,
      style: { stroke: color, strokeWidth, opacity: dim ? 0.15 : 1 },
      labelStyle: { fontSize: 10, fill: "#334155" },
      labelBgStyle: { fill: "#fff", opacity: 0.9 },
      markerEnd: { type: MarkerType.ArrowClosed, color },
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
  const [layingOut, setLayingOut] = useState(false);

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
          return {
            id: n.id,
            position: pos,
            data: {
              label: (
                <div style={{ padding: 2, lineHeight: 1.2 }}>
                  <div style={{ fontWeight: 600, fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {n.label}
                  </div>
                  <div style={{ fontSize: 10, opacity: 0.75 }}>
                    {n.type} · {n.size} {n.type === "entity" ? "txns" : n.type === "account" ? "txns" : "accts"}
                  </div>
                </div>
              ),
            },
            style: nodeStyle(n.type),
            draggable: true,
          };
        });
        setRfNodes(next);
        setRfEdges(buildEdges(filtered.edges, selectedNode?.id));
      })
      .catch((e) => console.error("ELK layout failed:", e))
      .finally(() => { if (!cancelled) setLayingOut(false); });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtered, layout]);

  // Dim non-incident edges when a node is selected.
  useEffect(() => {
    setRfEdges(buildEdges(filtered.edges, selectedNode?.id));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedNode]);

  const onNodeClick: NodeMouseHandler = useCallback((_e, node) => {
    const gn = data?.nodes.find((n) => n.id === node.id);
    if (gn) setSelectedNode(gn);
  }, [data]);

  if (isLoading) return <div className="bg-card border border-border rounded-lg p-8 text-muted-foreground">Loading graph…</div>;
  if (error) return <div className="bg-destructive/10 border border-destructive/40 rounded-lg p-6 text-destructive">Failed to load graph: {String(error)}</div>;
  if (!data) return null;

  return (
    <div className="space-y-3">
      {/* Filter bar */}
      <div className="bg-card border border-border rounded-lg p-3 flex items-center gap-4 flex-wrap text-sm">
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
            <option value="force">Force (organic)</option>
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
          gridTemplateColumns: selectedNode ? "1fr 380px" : "1fr 0px",
          transition: "grid-template-columns 180ms ease",
        }}
      >
        <div className="relative">
          <ReactFlow
            nodes={rfNodes}
            edges={rfEdges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            onPaneClick={() => setSelectedNode(null)}
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
                if (id.startsWith("person:")) return PALETTE.person.bg;
                if (id.startsWith("account:")) return PALETTE.account.bg;
                return PALETTE.entity.bg;
              }}
              pannable zoomable
            />
          </ReactFlow>
        </div>

        {selectedNode && (
          <NodeInspector
            node={selectedNode}
            edges={data.edges}
            onClose={() => setSelectedNode(null)}
            caseId={caseId}
          />
        )}
      </div>

      <div className="bg-background border border-border rounded-lg p-3 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">Legend:</span>{" "}
        <span style={{ color: PALETTE.person.bg }}>●</span> Person{"  "}
        <span style={{ color: PALETTE.account.bg }}>●</span> Account{"  "}
        <span style={{ color: "#cbd5e1" }}>●</span> Entity{"  "}·{"  "}
        <span style={{ color: "#dc2626" }}>→</span> flow out (debit){"  "}
        <span style={{ color: "#16a34a" }}>→</span> flow in (credit){"  "}
        <span style={{ color: "#94a3b8" }}>→</span> ownership{"  "}·{"  "}
        click a node to inspect
      </div>
    </div>
  );
}

function NodeInspector({
  node,
  edges,
  onClose,
  caseId,
}: {
  node: GraphNode;
  edges: GraphEdge[];
  onClose: () => void;
  caseId: string;
}) {
  const incident = edges.filter((e) => e.source === node.id || e.target === node.id);
  const flowIn = incident.filter((e) => e.kind === "flow_in" && e.target === node.id);
  const flowOut = incident.filter((e) => e.kind === "flow_out" && e.source === node.id);
  const totalIn = flowIn.reduce((s, e) => s + e.total_amount, 0);
  const totalOut = flowOut.reduce((s, e) => s + e.total_amount, 0);
  const palette = PALETTE[node.type as keyof typeof PALETTE];

  // Extract bare id from "account:a1" / "entity:e12" / "person:p1"
  const [kind, bareId] = node.id.split(":");

  const workbenchLink = (() => {
    if (kind === "account") return `/cases/${caseId}/workbench?account=${bareId}`;
    if (kind === "person" || kind === "entity") return `/cases/${caseId}/workbench`;
    return null;
  })();

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
        <div>
          <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">ID</div>
          <div className="font-mono text-foreground text-xs">{bareId}</div>
        </div>

        {node.type === "account" && (
          <>
            {node.meta.bank && (
              <div>
                <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Bank</div>
                <div className="text-foreground">{node.meta.bank} · {node.meta.type}</div>
              </div>
            )}
            {node.meta.holder_name && node.meta.holder_name !== "Unknown" && (
              <div>
                <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Holder</div>
                <div className="text-foreground">{node.meta.holder_name}</div>
              </div>
            )}
          </>
        )}

        {node.type === "entity" && Array.isArray(node.meta.aliases) && node.meta.aliases.length > 0 && (
          <div>
            <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Aliases</div>
            <div className="flex flex-wrap gap-1">
              {node.meta.aliases.slice(0, 8).map((a: string) => (
                <span key={a} className="text-xs px-1.5 py-0.5 bg-background border border-border rounded text-foreground">{a}</span>
              ))}
              {node.meta.aliases.length > 8 && <span className="text-xs text-muted-foreground">+{node.meta.aliases.length - 8}</span>}
            </div>
          </div>
        )}

        {(flowIn.length > 0 || flowOut.length > 0) && (
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-background border border-border rounded p-2">
              <div className="text-xs text-muted-foreground">Flow in</div>
              <div className="text-base font-semibold text-[color:var(--fl-emerald-500)] tabular-nums">{formatINR(totalIn)}</div>
              <div className="text-xs text-muted-foreground">{flowIn.reduce((s, e) => s + e.txn_count, 0)} txns</div>
            </div>
            <div className="bg-background border border-border rounded p-2">
              <div className="text-xs text-muted-foreground">Flow out</div>
              <div className="text-base font-semibold text-destructive tabular-nums">{formatINR(totalOut)}</div>
              <div className="text-xs text-muted-foreground">{flowOut.reduce((s, e) => s + e.txn_count, 0)} txns</div>
            </div>
          </div>
        )}

        {incident.length > 0 && (
          <div>
            <div className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
              Connected edges ({incident.length})
            </div>
            <div className="space-y-1 max-h-80 overflow-y-auto pr-1">
              {incident.slice(0, 50).map((e) => (
                <div key={e.id} className="text-xs border border-border rounded px-2 py-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-foreground">
                      {e.kind === "owns" ? "owns" : e.source === node.id ? "out →" : "← in"}
                    </span>
                    <span className="text-muted-foreground tabular-nums">
                      {e.kind !== "owns" && `${e.txn_count}× ${formatINR(e.total_amount)}`}
                    </span>
                  </div>
                  <div className="text-muted-foreground font-mono text-[10px] mt-0.5 truncate">
                    {e.source === node.id ? e.target : e.source}
                  </div>
                </div>
              ))}
              {incident.length > 50 && (
                <div className="text-xs text-muted-foreground">+{incident.length - 50} more</div>
              )}
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
