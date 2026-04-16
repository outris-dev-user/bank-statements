import { Link } from "react-router";
import { mockCases } from "../data/mockData";
import { Search, Plus, User } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

export function CaseDashboard() {
  return (
    <div className="min-h-screen bg-background">
      <header className="bg-card border-b border-border px-6 py-4">
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <h1 className="font-headline text-xl font-extrabold tracking-tight text-primary uppercase">LedgerFlow</h1>
          <div className="flex items-center gap-4">
            <button className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 flex items-center gap-2">
              <Plus className="w-4 h-4" />
              New Case
            </button>
            <button className="w-9 h-9 rounded-full bg-muted hover:bg-accent flex items-center justify-center">
              <User className="w-4 h-4 text-foreground" />
            </button>
          </div>
        </div>
      </header>

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

        <div className="bg-card rounded-lg border border-border divide-y divide-border">
          {mockCases.map((caseItem) => (
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
      </main>
    </div>
  );
}
