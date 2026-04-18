import {
  BaseEdge,
  EdgeLabelRenderer,
  getSmoothStepPath,
  type EdgeProps,
} from "@xyflow/react";

function formatINR(n: number): string {
  if (n >= 10_000_000) return `₹${(n / 10_000_000).toFixed(1)}Cr`;
  if (n >= 100_000) return `₹${(n / 100_000).toFixed(1)}L`;
  if (n >= 1_000) return `₹${(n / 1_000).toFixed(0)}k`;
  return `₹${n.toFixed(0)}`;
}

export function FlowEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  type,
  selected,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX, sourceY, sourcePosition,
    targetX, targetY, targetPosition,
    borderRadius: 14,
  });

  const d = data as
    | { totalAmount?: number; txnCount?: number; dim?: boolean }
    | undefined;
  const totalAmount = d?.totalAmount ?? 0;
  const txnCount = d?.txnCount ?? 0;

  const isFlow = type === "flow_in" || type === "flow_out";
  const baseThickness = isFlow
    ? Math.min(6, 1 + Math.log10(Math.max(1, totalAmount) / 1000))
    : 1;
  const thickness = selected ? baseThickness + 1.5 : baseThickness;

  const color =
    type === "flow_out" ? "#dc2626"
    : type === "flow_in" ? "var(--fl-emerald-500)"
    : "#94a3b8";

  const dashed = type === "owns";
  const opacity = d?.dim ? 0.12 : 1;

  // Bias the label toward the target end so parallel edges in opposite
  // directions (flow_in + flow_out between the same pair) land their labels
  // at opposite ends of the edge pair instead of stacking over each other.
  // 0 = midpoint, 1 = right at the target — 0.62 sits near the last bend.
  const END_BIAS = 0.62;
  const lx = labelX + (targetX - labelX) * END_BIAS;
  const ly = labelY + (targetY - labelY) * END_BIAS;

  // Per-colour SVG arrow marker. React-Flow dedupes <marker id=...> globally.
  const markerId = `flowarrow-${String(type)}`;

  return (
    <>
      <svg style={{ position: "absolute", width: 0, height: 0 }}>
        <defs>
          <marker
            id={markerId}
            viewBox="0 -5 10 10"
            refX="9"
            refY="0"
            markerUnits="strokeWidth"
            markerWidth={5}
            markerHeight={5}
            orient="auto"
          >
            <path d="M0,-4L9,0L0,4Z" fill={color} />
          </marker>
        </defs>
      </svg>
      {/* Invisible wide hit-area so thin edges are still easy to click.
          `<title>` renders as a native browser tooltip on hover. */}
      <path
        d={edgePath}
        fill="none"
        stroke="transparent"
        strokeWidth={Math.max(18, thickness + 16)}
        style={{ cursor: "pointer" }}
      >
        {isFlow && (
          <title>
            {type === "flow_out" ? "Out" : "In"}: {txnCount} txn{txnCount === 1 ? "" : "s"}
            {" · "}
            {formatINR(totalAmount)} — click to inspect
          </title>
        )}
        {!isFlow && <title>Ownership</title>}
      </path>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={`url(#${markerId})`}
        style={{
          stroke: color,
          strokeWidth: thickness,
          strokeDasharray: dashed ? "5 5" : undefined,
          opacity,
          pointerEvents: "none",
        }}
      />
      {isFlow && txnCount > 0 && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${lx}px,${ly}px)`,
              pointerEvents: "all",
              opacity,
              cursor: "pointer",
            }}
            className={
              "px-1.5 py-0.5 rounded border bg-card text-[10px] font-medium tabular-nums shadow-sm " +
              (selected ? "ring-2 ring-primary" : "")
            }
          >
            <span className="text-foreground">{txnCount}×</span>
            <span className="text-muted-foreground"> · </span>
            <span className="text-foreground">{formatINR(totalAmount)}</span>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
