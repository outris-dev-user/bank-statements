import { useState } from "react";
import { Link } from "react-router";
import { Search, Plus, User } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { useCases } from "../lib/queries";
import { NewCaseDialog } from "./NewCaseDialog";

export function CaseDashboard() {
  const { data: cases, isLoading, error } = useCases();
  const [showNewCase, setShowNewCase] = useState(false);

  return (
    <div className="min-h-screen bg-background">
      <header className="bg-card border-b border-border px-6 py-4">
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <h1 className="font-headline text-xl font-extrabold tracking-tight text-primary uppercase">LedgerFlow</h1>
          <div className="flex items-center gap-4">
            <button
              onClick={() => setShowNewCase(true)}
              className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 flex items-center gap-2"
            >
              <Plus className="w-4 h-4" />
              New Case
            </button>
            <button className="w-9 h-9 rounded-full bg-muted hover:bg-accent flex items-center justify-center">
              <User className="w-4 h-4 text-foreground" />
            </button>
          </div>
        </div>
      </header>

      {showNewCase && <NewCaseDialog onClose={() => setShowNewCase(false)} />}

      <main className="max-w-7xl mx-auto px-6 py-8">
        <div className="mb-6 flex items-center justify-between">
          <h2 className="text-2xl font-semibold text-foreground">Cases</h2>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search..."
              className="pl-10 pr-4 py-2 border border-border rounded-lg w-80 focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
        </div>

        {isLoading && (
          <div className="bg-card rounded-lg border border-border p-6 text-muted-foreground">Loading cases…</div>
        )}
        {error && (
          <div className="bg-destructive/10 border border-destructive/40 rounded-lg p-6 text-destructive">
            Failed to load: {String(error)}
          </div>
        )}

        {cases && cases.length === 0 && (
          <div className="bg-card rounded-lg border border-dashed border-border p-10 text-center">
            <div className="text-foreground font-medium mb-1">No cases yet</div>
            <div className="text-sm text-muted-foreground mb-4">
              Create a case to start uploading statements and tracking investigations.
            </div>
            <button
              onClick={() => setShowNewCase(true)}
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90"
            >
              <Plus className="w-4 h-4" />
              New Case
            </button>
          </div>
        )}

        {cases && cases.length > 0 && (
          <div className="bg-card rounded-lg border border-border divide-y divide-border">
            {cases.map((caseItem) => (
              <Link
                key={caseItem.id}
                to={`/cases/${caseItem.id}`}
                className="block p-6 hover:bg-background transition-colors"
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <h3 className="font-semibold text-foreground">{caseItem.fir_number}</h3>
                    <span className="flex items-center gap-1.5">
                      <span
                        className={`w-1.5 h-1.5 rounded-full ${
                          caseItem.status === 'active'
                            ? 'bg-[color:var(--fl-emerald-500)]'
                            : caseItem.status === 'closed'
                            ? 'bg-destructive'
                            : 'bg-muted-foreground'
                        }`}
                      />
                      <span className="text-sm text-muted-foreground capitalize">{caseItem.status}</span>
                    </span>
                  </div>
                  <span className="text-sm text-muted-foreground">
                    Updated {formatDistanceToNow(new Date(caseItem.updated_at), { addSuffix: true })}
                  </span>
                </div>
                <div className="text-foreground mb-2">{caseItem.title}</div>
                <div className="text-sm text-muted-foreground">
                  {caseItem.statement_count} statement{caseItem.statement_count !== 1 ? 's' : ''} ·{' '}
                  {caseItem.transaction_count} txns · {caseItem.flag_count} flags
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
