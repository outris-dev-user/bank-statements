import { Link, useParams, useSearchParams } from "react-router";
import { ChevronLeft, User, Search, Flag, Info, X, CheckCircle, Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import { TransactionTable } from "./TransactionTable";
import { EditDrawer } from "./EditDrawer";
import { MultiSelect } from "./MultiSelect";
import { SummaryView } from "./SummaryView";
import type { Transaction } from "../data";
import { useCase, useCaseTransactions, usePatchTransaction } from "../lib/queries";

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

function distinct(values: (string | undefined)[]): string[] {
  return Array.from(new Set(values.filter((v): v is string => !!v))).sort();
}

export function Workbench() {
  const { caseId } = useParams();
  const [searchParams] = useSearchParams();
  const accountParam = searchParams.get('account');

  const { data: detail, isLoading: loadingCase } = useCase(caseId);
  const [activeTab, setActiveTab] = useState<string>(accountParam || 'all');
  const [selectedTransaction, setSelectedTransaction] = useState<Transaction | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [lastAnchorId, setLastAnchorId] = useState<string | null>(null);
  const patchMut = usePatchTransaction();
  const [bulkBusy, setBulkBusy] = useState(false);

  // Filters
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<"all" | "Dr" | "Cr">("all");
  const [counterpartyFilter, setCounterpartyFilter] = useState<string[]>([]);
  const [categoryFilter, setCategoryFilter] = useState<string[]>([]);
  const [tagFilter, setTagFilter] = useState<string[]>([]);
  const [needsReviewOnly, setNeedsReviewOnly] = useState(false);
  const [flaggedOnly, setFlaggedOnly] = useState(false);

  const accountFilter = activeTab === 'all' ? undefined : activeTab;
  const { data: page, isLoading: loadingTxns } = useCaseTransactions(caseId, accountFilter);

  const accounts = detail?.accounts ?? [];
  const allTxns = useMemo(() => page?.items ?? [], [page]);

  const counterpartyOptions = useMemo(
    () => distinct(allTxns.map((t) => t.entities.counterparty?.value)),
    [allTxns],
  );
  const categoryOptions = useMemo(
    () => distinct(allTxns.map((t) => t.entities.category?.value)),
    [allTxns],
  );
  const tagOptions = useMemo(
    () => distinct(allTxns.flatMap((t) => t.tags)),
    [allTxns],
  );

  const isFlagged = (t: Transaction) =>
    t.review_status === "flagged" || t.flags.length > 0;

  const transactions = useMemo(() => {
    const q = search.trim().toLowerCase();
    const cpSet = new Set(counterpartyFilter);
    const catSet = new Set(categoryFilter);
    const tagSet = new Set(tagFilter);
    return allTxns.filter((t) => {
      if (typeFilter !== "all" && t.direction !== typeFilter) return false;
      if (cpSet.size > 0 && !cpSet.has(t.entities.counterparty?.value ?? "")) return false;
      if (catSet.size > 0 && !catSet.has(t.entities.category?.value ?? "")) return false;
      if (tagSet.size > 0 && !t.tags.some((tag) => tagSet.has(tag))) return false;
      if (needsReviewOnly && t.review_status === "reviewed") return false;
      if (flaggedOnly && !isFlagged(t)) return false;
      if (q) {
        const hay = [
          t.raw_description,
          t.entities.counterparty?.value ?? "",
          t.entities.category?.value ?? "",
          t.entities.channel?.value ?? "",
          t.tags.join(" "),
        ].join(" ").toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [allTxns, search, typeFilter, counterpartyFilter, categoryFilter, tagFilter, needsReviewOnly, flaggedOnly]);

  // Selection helpers. Shift-click extends from the last anchor to the
  // clicked row (in filtered order) — standard table multi-select pattern.
  const handleToggleSelect = (id: string, shiftKey: boolean) => {
    if (shiftKey && lastAnchorId) {
      const ids = transactions.map((t) => t.id);
      const a = ids.indexOf(lastAnchorId);
      const b = ids.indexOf(id);
      if (a !== -1 && b !== -1) {
        const [lo, hi] = a < b ? [a, b] : [b, a];
        const next = new Set(selectedIds);
        for (let i = lo; i <= hi; i++) next.add(ids[i]);
        setSelectedIds(next);
        setLastAnchorId(id);
        return;
      }
    }
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelectedIds(next);
    setLastAnchorId(id);
  };

  const handleToggleSelectAll = (ids: string[]) => {
    const allSelected = ids.every((id) => selectedIds.has(id));
    const next = new Set(selectedIds);
    if (allSelected) ids.forEach((id) => next.delete(id));
    else ids.forEach((id) => next.add(id));
    setSelectedIds(next);
  };

  const bulkSetStatus = async (status: "reviewed" | "flagged" | "unreviewed") => {
    if (bulkBusy || selectedIds.size === 0) return;
    setBulkBusy(true);
    try {
      await Promise.all(
        Array.from(selectedIds).map((id) =>
          patchMut.mutateAsync({ id, patch: { review_status: status } }),
        ),
      );
      setSelectedIds(new Set());
    } finally {
      setBulkBusy(false);
    }
  };

  if (loadingCase) return <div className="p-8 text-muted-foreground">Loading…</div>;
  if (!detail) return <div>Case not found</div>;
  const caseItem = detail.case;

  const currentAccount = activeTab !== 'all' ? accounts.find(a => a.id === activeTab) : null;

  const totalDebits = transactions.filter(t => t.direction === 'Dr').reduce((s, t) => s + t.amount, 0);
  const totalCredits = transactions.filter(t => t.direction === 'Cr').reduce((s, t) => s + t.amount, 0);

  const flaggedCountInScope = allTxns.filter(isFlagged).length;

  const activeFilterCount =
    (typeFilter !== "all" ? 1 : 0) +
    counterpartyFilter.length +
    categoryFilter.length +
    tagFilter.length +
    (needsReviewOnly ? 1 : 0) +
    (flaggedOnly ? 1 : 0) +
    (search.trim() ? 1 : 0);

  const resetFilters = () => {
    setSearch("");
    setTypeFilter("all");
    setCounterpartyFilter([]);
    setCategoryFilter([]);
    setTagFilter([]);
    setNeedsReviewOnly(false);
    setFlaggedOnly(false);
  };

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
          <button
            onClick={() => setActiveTab('summary')}
            className={`px-4 py-2 font-medium text-sm transition-colors relative ${
              activeTab === 'summary' ? 'text-primary' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            Summary
            {activeTab === 'summary' && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />}
          </button>
          <button className="px-4 py-2 font-medium text-sm text-muted-foreground relative flex items-center gap-1.5 group">
            Graph
            <Info className="w-3.5 h-3.5" />
            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-1.5 bg-slate-900 text-white text-xs rounded whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
              Coming in Phase 3
            </div>
          </button>
        </div>

        {activeTab === 'summary' ? (
          <SummaryView caseId={caseId!} />
        ) : (<>
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

        {/* Filter bar — fixed row of controls; Clear/Showing live in separate strip below. */}
        <div className="bg-card border border-border rounded-t-lg border-b-0 p-4">
          <div className="flex items-center gap-3">
            <div className="relative flex-1 min-w-[220px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search description, counterparty, tags…"
                className="w-full pl-10 pr-4 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value as any)}
              className={`px-3 py-2 border rounded-lg text-sm bg-card flex-shrink-0 ${
                typeFilter !== "all" ? "border-primary" : "border-border"
              }`}
            >
              <option value="all">Type ▾</option>
              <option value="Dr">Debits (Dr)</option>
              <option value="Cr">Credits (Cr)</option>
            </select>
            <MultiSelect
              label="Counterparty"
              options={counterpartyOptions}
              selected={counterpartyFilter}
              onChange={setCounterpartyFilter}
              width="w-44"
            />
            <MultiSelect
              label="Category"
              options={categoryOptions}
              selected={categoryFilter}
              onChange={setCategoryFilter}
              width="w-40"
            />
            <MultiSelect
              label="Tags"
              options={tagOptions}
              selected={tagFilter}
              onChange={setTagFilter}
              width="w-36"
            />
            <label className="flex items-center gap-2 text-sm text-muted-foreground flex-shrink-0">
              <input
                type="checkbox"
                checked={needsReviewOnly}
                onChange={(e) => setNeedsReviewOnly(e.target.checked)}
                className="rounded border-border"
              />
              Needs Review
            </label>
            <button
              onClick={() => setFlaggedOnly(!flaggedOnly)}
              disabled={flaggedCountInScope === 0 && !flaggedOnly}
              className={`flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border transition-colors flex-shrink-0 ${
                flaggedOnly
                  ? 'bg-amber-100 text-amber-800 border-amber-300'
                  : flaggedCountInScope > 0
                  ? 'bg-amber-50 text-amber-700 border-transparent hover:bg-amber-100'
                  : 'bg-muted text-muted-foreground border-transparent cursor-not-allowed'
              }`}
              title={flaggedCountInScope === 0 ? "No flagged rows" : "Toggle flagged-only"}
            >
              <Flag className="w-4 h-4" />
              {flaggedCountInScope} flags
            </button>
          </div>
        </div>

        {/* Secondary strip — always present so the filter bar above never shifts. */}
        <div className="bg-background border border-t-0 border-border rounded-b-lg px-4 py-2 mb-4 flex items-center justify-between min-h-[40px]">
          <div className="text-xs text-muted-foreground">
            {activeFilterCount > 0
              ? `Showing ${transactions.length} of ${allTxns.length} transactions`
              : `${allTxns.length} transactions`}
          </div>
          {activeFilterCount > 0 && (
            <button
              onClick={resetFilters}
              className="flex items-center gap-1 px-2 py-1 text-xs text-primary hover:text-primary/80"
            >
              <X className="w-3.5 h-3.5" />
              Clear all filters ({activeFilterCount})
            </button>
          )}
        </div>

        {selectedIds.size > 0 && (
          <div className="bg-primary/10 border border-primary rounded-lg px-4 py-2 mb-4 flex items-center justify-between">
            <div className="text-sm text-foreground font-medium">
              {selectedIds.size} row{selectedIds.size !== 1 ? "s" : ""} selected
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => bulkSetStatus("reviewed")}
                disabled={bulkBusy}
                className="px-3 py-1.5 text-sm border border-border bg-card rounded hover:bg-background flex items-center gap-1.5 disabled:opacity-50"
              >
                {bulkBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle className="w-3.5 h-3.5" />}
                Mark reviewed
              </button>
              <button
                onClick={() => bulkSetStatus("flagged")}
                disabled={bulkBusy}
                className="px-3 py-1.5 text-sm border border-border bg-card rounded hover:bg-background flex items-center gap-1.5 disabled:opacity-50"
              >
                {bulkBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Flag className="w-3.5 h-3.5" />}
                Flag
              </button>
              <button
                onClick={() => bulkSetStatus("unreviewed")}
                disabled={bulkBusy}
                className="px-3 py-1.5 text-sm border border-border bg-card rounded hover:bg-background disabled:opacity-50"
              >
                Unmark
              </button>
              <button
                onClick={() => setSelectedIds(new Set())}
                className="px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {loadingTxns ? (
          <div className="bg-card border border-border rounded-lg p-6 text-muted-foreground">Loading transactions…</div>
        ) : (
          <TransactionTable
            transactions={transactions}
            accountId={activeTab !== 'all' ? activeTab : undefined}
            onEditTransaction={setSelectedTransaction}
            selectedIds={selectedIds}
            onToggleSelect={handleToggleSelect}
            onToggleSelectAll={handleToggleSelectAll}
          />
        )}

        {activeTab === 'all' && !loadingTxns && (
          <div className="mt-4 text-sm text-muted-foreground bg-card border border-border rounded-lg p-4">
            Totals: {transactions.length} txns · In ₹{totalCredits.toLocaleString()} · Out ₹{totalDebits.toLocaleString()} · Net ₹{(totalCredits - totalDebits).toLocaleString()}
          </div>
        )}
        </>)}
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
