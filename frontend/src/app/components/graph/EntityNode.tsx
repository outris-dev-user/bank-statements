import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Flag, AlertTriangle, Coins } from "lucide-react";

// Per-subtype visual treatment. Utilities/salary/government are deliberately
// smaller and muted so they recede into the background; counterparties are
// the default human-of-interest and get full weight.
const SUBTYPE_STYLE: Record<
  string,
  { bg: string; border: string; fg: string; minWidth: number; fontSize: number }
> = {
  counterparty: { bg: "#475569", border: "#64748b", fg: "#fff", minWidth: 180, fontSize: 13 },
  merchant:     { bg: "#64748b", border: "#94a3b8", fg: "#fff", minWidth: 160, fontSize: 12 },
  bank:         { bg: "var(--fl-navy-700)", border: "var(--fl-navy-500)", fg: "#fff", minWidth: 160, fontSize: 12 },
  government:   { bg: "#b45309", border: "#d97706", fg: "#fff", minWidth: 140, fontSize: 11 },
  salary:       { bg: "var(--fl-emerald-500)", border: "var(--fl-emerald-300)", fg: "#fff", minWidth: 140, fontSize: 11 },
  finance:      { bg: "#3730a3", border: "#4338ca", fg: "#fff", minWidth: 160, fontSize: 12 },
  utility:      { bg: "#94a3b8", border: "#cbd5e1", fg: "#fff", minWidth: 120, fontSize: 11 },
  person:       { bg: "var(--fl-navy-600)", border: "var(--fl-navy-500)", fg: "#fff", minWidth: 160, fontSize: 12 },
  unknown:      { bg: "#64748b", border: "#94a3b8", fg: "#fff", minWidth: 160, fontSize: 12 },
};

export function EntityNode({ data, selected }: NodeProps) {
  const d = data as {
    label: string;
    sublabel?: string;
    entityType?: string;
    flagged?: boolean;
    needsReview?: boolean;
    highValue?: boolean;
    dim?: boolean;
  };
  const style = SUBTYPE_STYLE[d.entityType || "counterparty"] || SUBTYPE_STYLE.counterparty;

  // Badge priority: flagged > needs-review > high-value. Max one shown.
  let badge: React.ReactNode = null;
  if (d.flagged) {
    badge = (
      <div className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full flex items-center justify-center"
           style={{ background: "var(--fl-ruby-500)" }}>
        <Flag className="w-2.5 h-2.5 text-white" />
      </div>
    );
  } else if (d.needsReview) {
    badge = (
      <div className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full flex items-center justify-center bg-amber-500">
        <AlertTriangle className="w-2.5 h-2.5 text-white" />
      </div>
    );
  } else if (d.highValue) {
    badge = (
      <div className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full flex items-center justify-center bg-yellow-500">
        <Coins className="w-2.5 h-2.5 text-white" />
      </div>
    );
  }

  return (
    <div
      className="relative rounded-lg px-3 py-2 shadow-md border-2 transition-opacity"
      style={{
        background: style.bg,
        borderColor: selected ? "#fff" : style.border,
        color: style.fg,
        minWidth: style.minWidth,
        opacity: d.dim ? 0.25 : 1,
      }}
    >
      <Handle type="target" position={Position.Left} style={{ background: "#10b981" }} />
      <Handle type="source" position={Position.Right} style={{ background: "#ef4444" }} />
      {badge}
      <div
        className="font-semibold truncate leading-tight"
        title={d.label}
        style={{ fontSize: style.fontSize }}
      >
        {d.label}
      </div>
      {d.sublabel && (
        <div
          className="tabular-nums truncate opacity-80 leading-tight mt-0.5"
          style={{ fontSize: Math.max(10, style.fontSize - 2) }}
        >
          {d.sublabel}
        </div>
      )}
    </div>
  );
}
