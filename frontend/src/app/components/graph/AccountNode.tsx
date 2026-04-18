import { Handle, Position, type NodeProps } from "@xyflow/react";
import { CreditCard, Wallet, Landmark, Flag, AlertTriangle, Coins } from "lucide-react";

function iconFor(accountType?: string) {
  if (accountType === "CC") return CreditCard;
  if (accountType === "CA") return Landmark;
  return Wallet;
}

export function AccountNode({ data, selected }: NodeProps) {
  const d = data as {
    label: string;
    sublabel?: string;
    accountType?: string;
    flagged?: boolean;
    needsReview?: boolean;
    highValue?: boolean;
    flaggedCount?: number;
    totalAmount?: number;
    dim?: boolean;
  };
  const Icon = iconFor(d.accountType);

  // Same priority as EntityNode: flagged > needs-review > high-value.
  let badge: React.ReactNode = null;
  if (d.flagged) {
    const tip = d.flaggedCount
      ? `${d.flaggedCount} flagged transaction${d.flaggedCount === 1 ? "" : "s"} — click node to review & unflag`
      : "Has flagged transactions — click node to review";
    badge = (
      <div
        className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full flex items-center justify-center"
        style={{ background: "var(--fl-ruby-500)" }}
        title={tip}
      >
        <Flag className="w-2.5 h-2.5 text-white" />
      </div>
    );
  } else if (d.needsReview) {
    badge = (
      <div
        className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full flex items-center justify-center bg-amber-500"
        title="Needs review — pattern detector marked a transaction as needing attention"
      >
        <AlertTriangle className="w-2.5 h-2.5 text-white" />
      </div>
    );
  } else if (d.highValue) {
    badge = (
      <div
        className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full flex items-center justify-center bg-yellow-500"
        title="High-value node — total ≥ ₹10L"
      >
        <Coins className="w-2.5 h-2.5 text-white" />
      </div>
    );
  }

  const nodeTip = (() => {
    const parts: string[] = [d.label];
    if (d.accountType) parts.push(`(${d.accountType})`);
    if (typeof d.totalAmount === "number" && d.totalAmount > 0) {
      parts.push(`— ₹${d.totalAmount.toLocaleString("en-IN")} across ${d.sublabel ?? ""}`);
    }
    return parts.join(" ");
  })();

  return (
    <div
      className="relative rounded-lg px-4 py-2.5 shadow-md border-2 transition-opacity"
      style={{
        background: "#0e7490",
        borderColor: selected ? "#67e8f9" : "#0891b2",
        color: "#fff",
        minWidth: 220,
        opacity: d.dim ? 0.25 : 1,
      }}
      title={nodeTip}
    >
      <Handle type="target" position={Position.Left} style={{ background: "#22d3ee" }} />
      <Handle type="source" position={Position.Right} style={{ background: "#22d3ee" }} />
      {badge}
      <div className="flex items-center gap-2">
        <Icon className="w-4 h-4 opacity-85 flex-shrink-0" />
        <div className="font-semibold text-sm truncate">
          {d.label}
        </div>
      </div>
      {d.sublabel && (
        <div className="text-[11px] opacity-80 mt-0.5 tabular-nums truncate">{d.sublabel}</div>
      )}
    </div>
  );
}
