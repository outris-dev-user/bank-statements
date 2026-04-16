import { useMemo } from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend } from "recharts";
import { CheckCircle, Flag, AlertTriangle, Loader2, Zap, ShieldAlert, ShieldCheck } from "lucide-react";
import { useCaseSummary, useRunPatterns } from "../lib/queries";
import type { PatternHit } from "../lib/api";

const CATEGORY_COLORS = [
  "var(--fl-emerald-500)", "var(--fl-amber-500)", "var(--fl-navy-500)",
  "var(--fl-ruby-500)", "var(--fl-violet-500)", "var(--fl-teal-500)",
  "var(--fl-slate-500)", "var(--fl-slate-400)", "var(--fl-slate-300)",
];

const FALLBACK_COLORS = [
  "#2563eb", "#16a34a", "#d97706", "#dc2626", "#7c3aed",
  "#0891b2", "#64748b", "#94a3b8", "#cbd5e1",
];

function formatINR(n: number): string {
  return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

interface SummaryViewProps {
  caseId: string;
}

export function SummaryView({ caseId }: SummaryViewProps) {
  const { data, isLoading, error } = useCaseSummary(caseId);
  const runPatterns = useRunPatterns();

  const monthlyData = useMemo(
    () => (data?.monthly ?? []).map((m) => ({
      month: m.month,
      Debits: Math.round(m.dr_total),
      Credits: Math.round(m.cr_total),
    })),
    [data],
  );

  const pieData = useMemo(
    () => (data?.categories ?? []).map((c) => ({ name: c.category, value: c.count })),
    [data],
  );

  if (isLoading) return <div className="bg-card border border-border rounded-lg p-8 text-muted-foreground">Loading summary…</div>;
  if (error) return <div className="bg-destructive/10 border border-destructive/40 rounded-lg p-6 text-destructive">Failed to load summary: {String(error)}</div>;
  if (!data) return null;

  return (
    <div className="space-y-4">
      {/* KPI strip */}
      <div className="grid grid-cols-4 gap-4">
        <Kpi label="Credits in" value={formatINR(data.total_cr)} accent="text-[color:var(--fl-emerald-500)]" />
        <Kpi label="Debits out" value={formatINR(data.total_dr)} accent="text-destructive" />
        <Kpi label="Net" value={formatINR(data.net)} accent={data.net >= 0 ? "text-[color:var(--fl-emerald-500)]" : "text-destructive"} />
        <Kpi label="Transactions" value={data.txn_count.toLocaleString()} />
      </div>

      {/* Review status + run-patterns */}
      <div className="grid grid-cols-4 gap-4">
        <ReviewPill icon={<AlertTriangle className="w-4 h-4" />} label="Unreviewed" value={data.unreviewed_count} tone="amber" />
        <ReviewPill icon={<CheckCircle className="w-4 h-4" />} label="Reviewed" value={data.reviewed_count} tone="emerald" />
        <ReviewPill icon={<Flag className="w-4 h-4" />} label="Flagged" value={data.flagged_count} tone="ruby" />
        <ReviewPill icon={<Flag className="w-4 h-4" />} label="Extraction flags" value={data.flag_count} tone="navy" />
      </div>

      <div className="flex items-center justify-end">
        <button
          onClick={() => runPatterns.mutate(caseId)}
          disabled={runPatterns.isPending}
          className="px-3 py-2 text-sm border border-border bg-card rounded hover:bg-background flex items-center gap-2 disabled:opacity-50"
          title="Re-run structuring / velocity / round-amount detectors"
        >
          {runPatterns.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
          Re-run detectors
        </button>
      </div>

      {runPatterns.data && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-900 rounded-lg p-3 text-sm">
          Detectors applied:{" "}
          {Object.entries(runPatterns.data.flags_added).length === 0
            ? "no new flags"
            : Object.entries(runPatterns.data.flags_added).map(([k, n]) => `${k.replace(/_/g, " ").toLowerCase()}: ${n}`).join(" · ")}
        </div>
      )}

      {/* Forensic patterns — a scoreboard showing each detector's hit count */}
      <PatternsCard patterns={data.patterns} />

      {/* Monthly chart */}
      <div className="bg-card border border-border rounded-lg p-4">
        <h3 className="text-sm font-semibold text-foreground mb-3">Monthly credits vs debits</h3>
        <div style={{ width: "100%", height: 260 }}>
          <ResponsiveContainer>
            <BarChart data={monthlyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="month" tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} />
              <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} />
              <Tooltip formatter={(v: number) => formatINR(v)} />
              <Legend />
              <Bar dataKey="Credits" fill="#16a34a" />
              <Bar dataKey="Debits" fill="#dc2626" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Category pie */}
        <div className="bg-card border border-border rounded-lg p-4">
          <h3 className="text-sm font-semibold text-foreground mb-3">Categories</h3>
          <div style={{ width: "100%", height: 260 }}>
            <ResponsiveContainer>
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90} label>
                  {pieData.map((_, idx) => (
                    <Cell key={idx} fill={FALLBACK_COLORS[idx % FALLBACK_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Top counterparties */}
        <div className="bg-card border border-border rounded-lg p-4">
          <h3 className="text-sm font-semibold text-foreground mb-3">Top counterparties (by count)</h3>
          <div className="space-y-1.5 max-h-[260px] overflow-y-auto">
            {data.top_counterparties.map((cp) => (
              <div key={cp.name} className="flex items-center justify-between text-sm border-b border-border/50 py-1.5 last:border-0">
                <div className="truncate flex-1 mr-3 text-foreground" title={cp.name}>{cp.name}</div>
                <div className="flex items-center gap-3 text-xs tabular-nums">
                  <span className="text-muted-foreground">{cp.count}×</span>
                  {cp.total_dr > 0 && <span className="text-destructive">−{formatINR(cp.total_dr)}</span>}
                  {cp.total_cr > 0 && <span className="text-[color:var(--fl-emerald-500)]">+{formatINR(cp.total_cr)}</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function PatternsCard({ patterns }: { patterns: PatternHit[] }) {
  const total = patterns.reduce((s, p) => s + p.count, 0);
  const hit = patterns.filter((p) => p.count > 0);
  const quiet = patterns.filter((p) => p.count === 0);

  const severityBadge = (sev: string) => {
    if (sev === "high") return "bg-destructive/10 text-destructive border-destructive/30";
    if (sev === "medium") return "bg-amber-50 text-amber-800 border-amber-300";
    return "bg-slate-50 text-slate-700 border-slate-200";
  };

  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
          {total > 0 ? <ShieldAlert className="w-4 h-4 text-amber-600" /> : <ShieldCheck className="w-4 h-4 text-[color:var(--fl-emerald-500)]" />}
          Forensic patterns
          <span className="text-xs text-muted-foreground font-normal">{total} total hits across {patterns.length} detectors</span>
        </h3>
      </div>

      {hit.length === 0 ? (
        <div className="bg-background border border-border rounded-lg p-4 text-sm text-muted-foreground">
          No pattern hits yet. Detectors ran but didn't flag anything.
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          {hit.map((p) => (
            <div key={p.name} className={`border rounded-lg p-3 ${severityBadge(p.severity)}`}>
              <div className="flex items-center justify-between mb-1">
                <div className="text-sm font-medium">{p.label}</div>
                <div className="text-lg font-semibold tabular-nums">{p.count}</div>
              </div>
              <div className="text-xs opacity-80 leading-snug">{p.description}</div>
              {p.sample_txn_ids.length > 0 && (
                <div className="text-xs mt-2 font-mono opacity-70">
                  examples: {p.sample_txn_ids.slice(0, 3).join(", ")}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {quiet.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {quiet.map((p) => (
            <span
              key={p.name}
              className="text-xs px-2 py-1 rounded border border-border text-muted-foreground bg-background"
              title={p.description}
            >
              <ShieldCheck className="w-3 h-3 inline mr-1" />
              {p.label}: 0
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function Kpi({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <div className="text-xs text-muted-foreground uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-2xl font-semibold tabular-nums ${accent ?? "text-foreground"}`}>{value}</div>
    </div>
  );
}

function ReviewPill({ icon, label, value, tone }: { icon: React.ReactNode; label: string; value: number; tone: "emerald" | "amber" | "ruby" | "navy" }) {
  const toneMap = {
    emerald: "text-[color:var(--fl-emerald-500)] border-[color:var(--fl-emerald-500)]/30",
    amber:   "text-amber-700 border-amber-300",
    ruby:    "text-destructive border-destructive/30",
    navy:    "text-primary border-primary/30",
  } as const;
  return (
    <div className={`bg-card border rounded-lg p-3 flex items-center gap-3 ${toneMap[tone]}`}>
      <div>{icon}</div>
      <div>
        <div className="text-xs uppercase tracking-wider">{label}</div>
        <div className="text-lg font-semibold tabular-nums text-foreground">{value.toLocaleString()}</div>
      </div>
    </div>
  );
}
