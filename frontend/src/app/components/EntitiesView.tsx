import { useMemo, useState } from "react";
import { Search, Zap, Loader2, ChevronRight, Users, X } from "lucide-react";
import { useEntities, useEntity, useResolveEntities } from "../lib/queries";

interface EntitiesViewProps {
  caseId: string;
}

function formatINR(n: number): string {
  return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

export function EntitiesView({ caseId }: EntitiesViewProps) {
  const { data: entities, isLoading } = useEntities(caseId);
  const resolveMut = useResolveEntities();
  const [query, setQuery] = useState("");
  const [openEntityId, setOpenEntityId] = useState<string | null>(null);

  const filtered = useMemo(() => {
    if (!entities) return [];
    const q = query.trim().toLowerCase();
    const list = q
      ? entities.filter(
          (e) =>
            e.name.toLowerCase().includes(q) ||
            e.aliases.some((a) => a.toLowerCase().includes(q)),
        )
      : entities;
    return [...list].sort((a, b) => b.txn_count - a.txn_count);
  }, [entities, query]);

  if (isLoading) {
    return <div className="bg-card border border-border rounded-lg p-8 text-muted-foreground">Loading entities…</div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search entities…"
            className="w-full pl-10 pr-4 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
        <button
          onClick={() => resolveMut.mutate(caseId)}
          disabled={resolveMut.isPending}
          className="px-3 py-2 text-sm border border-border bg-card rounded hover:bg-background flex items-center gap-2 disabled:opacity-50"
          title="Re-cluster counterparties based on canonical keys"
        >
          {resolveMut.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
          Re-run resolver
        </button>
      </div>

      {resolveMut.data && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-900 rounded-lg p-3 text-sm">
          Resolver ran: {resolveMut.data.entities_created} new · {resolveMut.data.entities_updated} updated · {resolveMut.data.groups} groups
        </div>
      )}

      <div className="bg-card border border-border rounded-lg">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Users className="w-4 h-4" />
            {filtered.length} entit{filtered.length === 1 ? "y" : "ies"}
          </h3>
          <div className="text-xs text-muted-foreground">Click a row for details</div>
        </div>
        <div className="divide-y divide-border max-h-[60vh] overflow-y-auto">
          {filtered.map((e) => (
            <button
              key={e.id}
              onClick={() => setOpenEntityId(e.id)}
              className="w-full px-4 py-3 text-left hover:bg-background flex items-center justify-between gap-4"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <div className="font-medium text-foreground truncate">{e.name}</div>
                  {e.entity_type && (
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wide font-semibold ${
                        e.entity_type === 'self'
                          ? 'bg-blue-100 text-blue-700'
                          : e.entity_type === 'related_party'
                          ? 'bg-purple-100 text-purple-700'
                          : e.entity_type === 'government'
                          ? 'bg-orange-100 text-orange-700'
                          : e.entity_type === 'bank'
                          ? 'bg-slate-200 text-slate-700'
                          : e.entity_type === 'business' || e.entity_type === 'merchant'
                          ? 'bg-emerald-50 text-emerald-700'
                          : e.entity_type === 'individual'
                          ? 'bg-emerald-100 text-emerald-700'
                          : 'bg-gray-100 text-gray-600'
                      }`}
                      title={`Entity type: ${e.entity_type}`}
                    >
                      {e.entity_type.replace('_', ' ')}
                    </span>
                  )}
                  {!e.auto_created && (
                    <span className="text-xs px-1.5 py-0.5 bg-primary/10 text-primary rounded">manual</span>
                  )}
                  {e.aliases.length > 0 && (
                    <span className="text-xs text-muted-foreground">+{e.aliases.length} alias{e.aliases.length > 1 ? "es" : ""}</span>
                  )}
                </div>
                <div className="text-xs text-muted-foreground truncate font-mono mt-0.5">key: {e.canonical_key}</div>
              </div>
              <div className="flex items-center gap-4 text-sm tabular-nums flex-shrink-0">
                <span className="text-muted-foreground">{e.txn_count} txns</span>
                {e.total_dr > 0 && <span className="text-destructive">−{formatINR(e.total_dr)}</span>}
                {e.total_cr > 0 && <span className="text-[color:var(--fl-emerald-500)]">+{formatINR(e.total_cr)}</span>}
                <ChevronRight className="w-4 h-4 text-muted-foreground" />
              </div>
            </button>
          ))}
          {filtered.length === 0 && (
            <div className="px-4 py-8 text-center text-sm text-muted-foreground">
              {query ? "No entities match your search." : "No entities yet. Upload statements or run the resolver."}
            </div>
          )}
        </div>
      </div>

      {openEntityId && (
        <EntityDrawer entityId={openEntityId} onClose={() => setOpenEntityId(null)} />
      )}
    </div>
  );
}

function EntityDrawer({ entityId, onClose }: { entityId: string; onClose: () => void }) {
  const { data, isLoading } = useEntity(entityId);

  return (
    <div className="fixed inset-y-0 right-0 w-[600px] bg-card shadow-2xl border-l border-border z-50 flex flex-col">
      <div className="border-b border-border px-6 py-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-foreground">Entity detail</h2>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
          <X className="w-5 h-5" />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-5">
        {isLoading && <div className="text-muted-foreground">Loading…</div>}
        {data && (
          <>
            <div>
              <div className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Name</div>
              <div className="text-xl font-semibold text-foreground">{data.entity.name}</div>
              <div className="text-xs text-muted-foreground font-mono mt-1">canonical: {data.entity.canonical_key}</div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <Stat label="Transactions" value={data.entity.txn_count.toString()} />
              <Stat label="Total debits" value={formatINR(data.entity.total_dr)} tone="destructive" />
              <Stat label="Total credits" value={formatINR(data.entity.total_cr)} tone="emerald" />
            </div>

            {data.entity.aliases.length > 0 && (
              <div>
                <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Aliases ({data.entity.aliases.length})</div>
                <div className="flex flex-wrap gap-1.5">
                  {data.entity.aliases.map((a) => (
                    <span key={a} className="text-xs px-2 py-1 bg-background border border-border rounded text-foreground">{a}</span>
                  ))}
                </div>
              </div>
            )}

            <div>
              <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Linked transactions</div>
              <div className="border border-border rounded-lg divide-y divide-border max-h-[50vh] overflow-y-auto">
                {data.transactions.map((t) => (
                  <div key={t.id} className="px-3 py-2 flex items-center justify-between text-sm">
                    <div className="min-w-0 flex-1 mr-3">
                      <div className="flex items-center gap-2 text-foreground">
                        <span className="text-xs text-muted-foreground tabular-nums">
                          {new Date(t.txn_date).toLocaleDateString("en-GB")}
                        </span>
                        <span className="truncate">{t.raw_description}</span>
                      </div>
                    </div>
                    <div className="flex-shrink-0 tabular-nums text-sm">
                      {t.direction === "Dr" ? (
                        <span className="text-destructive">−{formatINR(t.amount)}</span>
                      ) : (
                        <span className="text-[color:var(--fl-emerald-500)]">+{formatINR(t.amount)}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "destructive" | "emerald" }) {
  const toneCls = tone === "destructive" ? "text-destructive" : tone === "emerald" ? "text-[color:var(--fl-emerald-500)]" : "text-foreground";
  return (
    <div className="bg-background border border-border rounded-lg p-3">
      <div className="text-xs text-muted-foreground uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-lg font-semibold tabular-nums ${toneCls}`}>{value}</div>
    </div>
  );
}
