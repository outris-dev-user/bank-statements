import { useMemo, useState } from "react";
import { Loader2, Filter } from "lucide-react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useCaseGraph } from "../lib/queries";
import type { GraphNode, GraphEdge } from "../lib/api";

interface GraphViewProps {
  caseId: string;
}

const PALETTE = {
  person:  { bg: "#1e3a8a", text: "#fff", border: "#1e40af" },   // navy
  account: { bg: "#0891b2", text: "#fff", border: "#0e7490" },   // teal
  entity:  { bg: "#f1f5f9", text: "#1e293b", border: "#cbd5e1" }, // slate
};

function formatINR(n: number): string {
  if (n >= 10_000_000) return `₹${(n / 10_000_000).toFixed(1)}Cr`;
  if (n >= 100_000) return `₹${(n / 100_000).toFixed(1)}L`;
  if (n >= 1_000) return `₹${(n / 1_000).toFixed(0)}k`;
  return `₹${n.toFixed(0)}`;
}

/**
 * Lay out nodes using three vertical lanes: persons on the left, accounts
 * in the middle, entities on the right. Good enough for Phase 3 scaffolding
 * — layouts like Dagre / force-directed come later.
 */
function layoutLanes(nodes: GraphNode[]): Node[] {
  const byType: Record<string, GraphNode[]> = { person: [], account: [], entity: [] };
  for (const n of nodes) byType[n.type].push(n);

  // Sort entities by size desc so the biggest ones sit near the top.
  byType.entity.sort((a, b) => b.size - a.size);

  const lane = { person: 0, account: 400, entity: 800 };
  const vSpacing = 80;

  const out: Node[] = [];
  for (const type of ["person", "account", "entity"] as const) {
    const group = byType[type];
    group.forEach((n, i) => {
      const palette = PALETTE[type];
      out.push({
        id: n.id,
        type: "default",
        position: { x: lane[type], y: i * vSpacing },
        data: {
          label: (
            <div style={{ padding: 2 }}>
              <div style={{ fontWeight: 600, fontSize: 12 }}>{n.label.slice(0, 32)}</div>
              <div style={{ fontSize: 10, opacity: 0.7 }}>
                {type} · {n.size} txns
              </div>
            </div>
          ),
        },
        style: {
          background: palette.bg,
          color: palette.text,
          border: `1px solid ${palette.border}`,
          borderRadius: 6,
          width: 240,
          fontSize: 12,
        },
      });
    });
  }
  return out;
}

function mapEdges(edges: GraphEdge[]): Edge[] {
  return edges.map((e) => {
    const isFlow = e.kind !== "owns";
    const strokeWidth = isFlow ? Math.min(6, 1 + Math.log10(Math.max(1, e.total_amount) / 1000)) : 1;
    const color =
      e.kind === "flow_out" ? "#dc2626"
      : e.kind === "flow_in" ? "#16a34a"
      : "#94a3b8";
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      label: isFlow ? `${e.txn_count}× ${formatINR(e.total_amount)}` : undefined,
      animated: false,
      style: { stroke: color, strokeWidth },
      labelStyle: { fontSize: 10, fill: "#334155" },
      labelBgStyle: { fill: "#fff", opacity: 0.9 },
    };
  });
}

export function GraphView({ caseId }: GraphViewProps) {
  const { data, isLoading, error } = useCaseGraph(caseId);
  const [showPersons, setShowPersons] = useState(true);
  const [showAccounts, setShowAccounts] = useState(true);
  const [showEntities, setShowEntities] = useState(true);
  const [minAmount, setMinAmount] = useState(10_000);

  const filtered = useMemo(() => {
    if (!data) return { nodes: [] as GraphNode[], edges: [] as GraphEdge[] };
    const nodes = data.nodes.filter((n) => {
      if (n.type === "person") return showPersons;
      if (n.type === "account") return showAccounts;
      if (n.type === "entity") return showEntities;
      return true;
    });
    const nodeIds = new Set(nodes.map((n) => n.id));
    const edges = data.edges.filter((e) => {
      if (!nodeIds.has(e.source) || !nodeIds.has(e.target)) return false;
      if (e.kind === "owns") return true;
      return e.total_amount >= minAmount;
    });
    return { nodes, edges };
  }, [data, showPersons, showAccounts, showEntities, minAmount]);

  const rfNodes = useMemo(() => layoutLanes(filtered.nodes), [filtered.nodes]);
  const rfEdges = useMemo(() => mapEdges(filtered.edges), [filtered.edges]);

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
          <span className="text-muted-foreground">Min flow amount:</span>
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
        <div className="ml-auto text-xs text-muted-foreground">
          {filtered.nodes.length} nodes · {filtered.edges.length} edges shown
        </div>
      </div>

      {/* Canvas */}
      <div className="bg-card border border-border rounded-lg" style={{ height: "70vh" }}>
        <ReactFlow
          nodes={rfNodes}
          edges={rfEdges}
          fitView
          minZoom={0.1}
          maxZoom={2}
          nodesDraggable
        >
          <Background gap={16} color="#e2e8f0" />
          <Controls />
          <MiniMap
            nodeColor={(n) => {
              const id = n.id;
              if (id.startsWith("person:")) return PALETTE.person.bg;
              if (id.startsWith("account:")) return PALETTE.account.bg;
              return PALETTE.entity.bg;
            }}
            pannable zoomable
          />
        </ReactFlow>
      </div>

      <div className="bg-background border border-border rounded-lg p-3 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">Legend:</span>{" "}
        <span style={{ color: PALETTE.person.bg }}>●</span> Person{"  "}
        <span style={{ color: PALETTE.account.bg }}>●</span> Account{"  "}
        <span style={{ color: "#cbd5e1" }}>●</span> Entity{"  "}·{"  "}
        <span style={{ color: "#dc2626" }}>→</span> flow out (debit){"  "}
        <span style={{ color: "#16a34a" }}>→</span> flow in (credit){"  "}
        <span style={{ color: "#94a3b8" }}>→</span> ownership
      </div>
    </div>
  );
}
