import { Link, useParams, useSearchParams } from "react-router";
import { ChevronLeft, User, Search, Filter, Flag, Info } from "lucide-react";
import { useMemo, useState } from "react";
import { TransactionTable } from "./TransactionTable";
import { EditDrawer } from "./EditDrawer";
import type { Transaction } from "../data";
import { useCase, useCaseTransactions } from "../lib/queries";

function shortBankLabel(bank: string, accountType: string): string {
  const b = bank.toLowerCase();
  const short =
    b.includes('hdfc') ? 'HDFC' :
    b.includes('kotak') ? 'Kotak' :
    b.includes('icici') ? 'ICICI' :
    b.includes('idfc') ? 'IDFC' :
    b.includes('sbi') ? 'SBI' :
    b.includes('axis') ? 'Axis' :
    bank.split(' ')[0];
  return `${short} ${accountType}`;
}

export function Workbench() {
  const { caseId } = useParams();
  const [searchParams] = useSearchParams();
  const accountParam = searchParams.get('account');

  const { data: detail, isLoading: loadingCase } = useCase(caseId);
  const [activeTab, setActiveTab] = useState<string>(accountParam || 'all');
  const [selectedTransaction, setSelectedTransaction] = useState<Transaction | null>(null);

  const accountFilter = activeTab === 'all' ? undefined : activeTab;
  const { data: page, isLoading: loadingTxns } = useCaseTransactions(caseId, accountFilter);

  const accounts = detail?.accounts ?? [];
  const transactions = useMemo(() => page?.items ?? [], [page]);

  if (loadingCase) return <div className="p-8 text-muted-foreground">Loading…</div>;
  if (!detail) return <div>Case not found</div>;
  const caseItem = detail.case;

  const currentAccount = activeTab !== 'all' ? accounts.find(a => a.id === activeTab) : null;

  const flaggedCount = transactions.filter(t => t.flags.length > 0).length;
  const totalDebits = transactions.filter(t => t.direction === 'Dr').reduce((s, t) => s + t.amount, 0);
  const totalCredits = transactions.filter(t => t.direction === 'Cr').reduce((s, t) => s + t.amount, 0);

  return (
    <div className="min-h-screen bg-background">
      <header className="bg-card border-b border-border px-6 py-4">
        <div className="flex items-center justify-between max-w-[1600px] mx-auto">
          <div className="flex items-center gap-4">
            <Link to={`/cases/${caseId}`} className="text-muted-foreground hover:text-foreground">
              <ChevronLeft className="w-5 h-5" />
            </Link>
            <h1 className="text-lg font-semibold text-foreground">
              {caseItem.fir_number} · {caseItem.title.split(' — ')[0]}
            </h1>
          </div>
          <button className="w-9 h-9 rounded-full bg-muted hover:bg-accent flex items-center justify-center">
            <User className="w-4 h-4 text-foreground" />
          </button>
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto px-6 py-6">
        <div className="flex items-center gap-1 mb-6 border-b border-border">
          <button
            onClick={() => setActiveTab('all')}
            className={`px-4 py-2 font-medium text-sm transition-colors relative ${
              activeTab === 'all' ? 'text-primary' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            All transactions
            {activeTab === 'all' && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />}
          </button>
          {accounts.map((account) => (
            <button
              key={account.id}
              onClick={() => setActiveTab(account.id)}
              className={`px-4 py-2 font-medium text-sm transition-colors relative ${
                activeTab === account.id ? 'text-primary' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {shortBankLabel(account.bank, account.account_type)} {account.account_number.slice(-4)}
              {activeTab === account.id && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />}
            </button>
          ))}
          <button className="px-4 py-2 font-medium text-sm text-muted-foreground relative">Summary</button>
          <button className="px-4 py-2 font-medium text-sm text-muted-foreground relative flex items-center gap-1.5 group">
            Graph
            <Info className="w-3.5 h-3.5" />
            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-1.5 bg-slate-900 text-white text-xs rounded whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
              Coming in Phase 3
            </div>
          </button>
        </div>

        {currentAccount && (
          <div className="bg-card border border-border rounded-lg p-4 mb-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium text-foreground mb-1">
                  {currentAccount.bank} A/C {currentAccount.account_number} · {currentAccount.holder_name} · {currentAccount.account_type} · {currentAccount.currency}
                </div>
                <div className="text-sm text-muted-foreground">
                  {transactions.length} txns ·
                  Dr ₹{totalDebits.toLocaleString()} ·
                  Cr ₹{totalCredits.toLocaleString()} ·
                  Bal ₹{transactions[0]?.running_balance.toLocaleString() ?? 0}
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="bg-card border border-border rounded-lg p-4 mb-4">
          <div className="flex items-center gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search..."
                className="w-full pl-10 pr-4 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <select className="px-3 py-2 border border-border rounded-lg text-sm">
              <option>Type ▾</option><option>Dr</option><option>Cr</option>
            </select>
            <select className="px-3 py-2 border border-border rounded-lg text-sm"><option>Counterparty ▾</option></select>
            <select className="px-3 py-2 border border-border rounded-lg text-sm"><option>Category ▾</option></select>
            <select className="px-3 py-2 border border-border rounded-lg text-sm"><option>Tags ▾</option></select>
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <input type="checkbox" className="rounded border-border" />
              Needs Review
            </label>
            {flaggedCount > 0 && (
              <button className="flex items-center gap-1.5 px-3 py-2 text-sm text-amber-700 bg-amber-50 rounded-lg hover:bg-amber-200">
                <Flag className="w-4 h-4" />
                {flaggedCount} flags
              </button>
            )}
          </div>
        </div>

        {loadingTxns ? (
          <div className="bg-card border border-border rounded-lg p-6 text-muted-foreground">Loading transactions…</div>
        ) : (
          <TransactionTable
            transactions={transactions}
            accountId={activeTab !== 'all' ? activeTab : undefined}
            onEditTransaction={setSelectedTransaction}
          />
        )}

        {activeTab === 'all' && !loadingTxns && (
          <div className="mt-4 text-sm text-muted-foreground bg-card border border-border rounded-lg p-4">
            Summary: {transactions.length} txns · In ₹{totalCredits.toLocaleString()} · Out ₹{totalDebits.toLocaleString()} · Net ₹{(totalCredits - totalDebits).toLocaleString()}
          </div>
        )}
      </main>

      {selectedTransaction && (
        <EditDrawer
          transaction={selectedTransaction}
          onClose={() => setSelectedTransaction(null)}
        />
      )}
    </div>
  );
}
