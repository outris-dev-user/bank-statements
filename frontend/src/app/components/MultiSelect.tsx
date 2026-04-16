import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, X } from "lucide-react";

interface MultiSelectProps {
  label: string;
  options: string[];
  selected: string[];
  onChange: (values: string[]) => void;
  width?: string;
  maxMenuHeight?: number;
}

export function MultiSelect({
  label,
  options,
  selected,
  onChange,
  width = "w-48",
  maxMenuHeight = 280,
}: MultiSelectProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const toggle = (v: string) => {
    if (selected.includes(v)) onChange(selected.filter((x) => x !== v));
    else onChange([...selected, v]);
  };

  const display =
    selected.length === 0
      ? `${label} ▾`
      : selected.length === 1
      ? selected[0].length > 18
        ? selected[0].slice(0, 18) + "…"
        : selected[0]
      : `${label}: ${selected.length}`;

  const filtered = query.trim()
    ? options.filter((o) => o.toLowerCase().includes(query.toLowerCase()))
    : options;

  return (
    <div ref={ref} className={`relative ${width}`}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={`w-full px-3 py-2 border rounded-lg text-sm bg-card flex items-center justify-between gap-2 ${
          selected.length > 0 ? "border-primary text-foreground" : "border-border text-muted-foreground"
        }`}
      >
        <span className="truncate">{display}</span>
        {selected.length > 0 ? (
          <span
            role="button"
            tabIndex={0}
            onClick={(e) => { e.stopPropagation(); onChange([]); }}
            className="flex-shrink-0 hover:text-foreground"
            title="Clear selection"
          >
            <X className="w-3.5 h-3.5" />
          </span>
        ) : (
          <ChevronDown className="w-3.5 h-3.5 flex-shrink-0" />
        )}
      </button>

      {open && (
        <div className="absolute top-full left-0 mt-1 w-[260px] bg-card border border-border rounded-lg shadow-lg z-40">
          <div className="p-2 border-b border-border">
            <input
              autoFocus
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter…"
              className="w-full px-2 py-1.5 border border-border rounded text-sm bg-background focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <div className="overflow-y-auto py-1" style={{ maxHeight: maxMenuHeight }}>
            {filtered.length === 0 ? (
              <div className="px-3 py-2 text-xs text-muted-foreground">No matches</div>
            ) : (
              filtered.map((opt) => {
                const isSel = selected.includes(opt);
                return (
                  <button
                    key={opt}
                    onClick={() => toggle(opt)}
                    className="w-full px-3 py-1.5 text-left text-sm flex items-center gap-2 hover:bg-background"
                  >
                    <span
                      className={`w-4 h-4 border rounded flex items-center justify-center flex-shrink-0 ${
                        isSel ? "bg-primary border-primary" : "border-border"
                      }`}
                    >
                      {isSel && <Check className="w-3 h-3 text-white" />}
                    </span>
                    <span className="truncate text-foreground" title={opt}>{opt}</span>
                  </button>
                );
              })
            )}
          </div>
          {selected.length > 0 && (
            <div className="p-2 border-t border-border flex items-center justify-between">
              <span className="text-xs text-muted-foreground">{selected.length} selected</span>
              <button
                onClick={() => onChange([])}
                className="text-xs text-primary hover:text-primary/80"
              >
                Clear
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
