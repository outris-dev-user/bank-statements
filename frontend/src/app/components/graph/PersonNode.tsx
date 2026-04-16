import { Handle, Position, type NodeProps } from "@xyflow/react";
import { User } from "lucide-react";

export function PersonNode({ data, selected }: NodeProps) {
  const d = data as {
    label: string;
    sublabel?: string;
    dim?: boolean;
  };
  return (
    <div
      className="rounded-lg px-4 py-2.5 shadow-md border-2 transition-opacity"
      style={{
        background: "var(--fl-navy-800)",
        borderColor: selected ? "var(--fl-navy-300)" : "var(--fl-navy-700)",
        color: "#fff",
        minWidth: 200,
        opacity: d.dim ? 0.25 : 1,
      }}
    >
      <Handle type="source" position={Position.Right} style={{ background: "var(--fl-navy-500)" }} />
      <div className="flex items-center gap-2">
        <User className="w-4 h-4 opacity-80 flex-shrink-0" />
        <div
          className="font-semibold text-sm truncate"
          title={d.label}
          style={{ fontFamily: "var(--font-headline)" }}
        >
          {d.label}
        </div>
      </div>
      {d.sublabel && (
        <div className="text-[11px] opacity-70 mt-0.5 tabular-nums truncate">{d.sublabel}</div>
      )}
    </div>
  );
}
