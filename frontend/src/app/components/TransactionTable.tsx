import { useState, useRef, useEffect } from "react";
import React from "react";
import { Flag, CheckCircle, Loader2 } from "lucide-react";
import type { Transaction } from "../data";
import { usePatchTransaction } from "../lib/queries";
import { CATEGORIES } from "../lib/constants";

interface TransactionTableProps {
  transactions: Transaction[];
  accountId?: string;
  onEditTransaction: (transaction: Transaction) => void;
  selectedIds: Set<string>;
  onToggleSelect: (id: string, multi: boolean) => void;
  onToggleSelectAll: (ids: string[]) => void;
}

type InlineField = "counterparty" | "category" | "debit" | "credit";

interface InlineEditState {
  txnId: string;
  field: InlineField;
  value: string;
}

export function TransactionTable({
  transactions,
  accountId,
  onEditTransaction,
  selectedIds,
  onToggleSelect,
  onToggleSelectAll,
}: TransactionTableProps) {
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [inlineEdit, setInlineEdit] = useState<InlineEditState | null>(null);
  const patchMut = usePatchTransaction();
  const inputRef = useRef<HTMLInputElement | HTMLSelectElement>(null);

  useEffect(() => {
    if (inlineEdit && inputRef.current) {
      inputRef.current.focus();
      if (inputRef.current instanceof HTMLInputElement) inputRef.current.select();
    }
  }, [inlineEdit]);

  const toggleExpand = (txnId: string) => {
    const next = new Set(expandedRows);
    if (next.has(txnId)) next.delete(txnId); else next.add(txnId);
    setExpandedRows(next);
  };

  const getFlagIcon = (txn: Transaction) => {
    if (txn.review_status === "flagged") return <Flag className="w-4 h-4 text-destructive fill-destructive" />;
    if (txn.flags.includes('SUM_CHECK_CONTRIBUTOR')) return <Flag className="w-4 h-4 text-destructive fill-destructive" />;
    if (txn.flags.includes('NEEDS_REVIEW') || (txn.review_status === "unreviewed" && txn.flags.length > 0)) {
      return <Flag className="w-4 h-4 text-amber-600 fill-amber-600" />;
    }
    return <Flag className="w-4 h-4 text-muted-foreground/30" />;
  };

  const toggleFlag = (txn: Transaction) => {
    patchMut.mutate({
      id: txn.id,
      patch: { review_status: txn.review_status === "flagged" ? "unreviewed" : "flagged" },
    });
  };

  const startInline = (txn: Transaction, field: InlineField) => {
    let value = "";
    if (field === "counterparty" || field === "category") {
      value = txn.entities[field]?.value ?? "";
    } else if (field === "debit" || field === "credit") {
      value = txn.amount.toString();
    }
    setInlineEdit({ txnId: txn.id, field, value });
  };

  const commitInline = (txn: Transaction) => {
    if (!inlineEdit) return;
    const field = inlineEdit.field;

    if (field === "counterparty" || field === "category") {
      const nextValue = inlineEdit.value.trim();
      const prevValue = txn.entities[field]?.value ?? "";
      if (nextValue === prevValue) { setInlineEdit(null); return; }
      const nextEntities = {
        ...txn.entities,
        [field]: { value: nextValue, source: "user_edited" as const, confidence: 1.0 },
      };
      patchMut.mutate(
        { id: txn.id, patch: { entities: nextEntities } },
        { onSettled: () => setInlineEdit(null) },
      );
      return;
    }

    // debit / credit — numeric. User can change sign by moving value between
    // columns (editing the empty column implies switching direction).
    const num = Number(inlineEdit.value.replace(/,/g, ""));
    if (!isFinite(num) || num < 0) { setInlineEdit(null); return; }

    const desiredDir = field === "debit" ? "Dr" : "Cr";
    const sameAsBefore = num === txn.amount && desiredDir === txn.direction;
    if (sameAsBefore) { setInlineEdit(null); return; }

    patchMut.mutate(
      { id: txn.id, patch: { amount: num, direction: desiredDir } as any },
      { onSettled: () => setInlineEdit(null) },
    );
  };

  const baseBox = "block w-full px-1.5 py-0.5 rounded text-sm box-border border";

  const renderTextCell = (txn: Transaction, field: "counterparty") => {
    const isEditing = inlineEdit?.txnId === txn.id && inlineEdit.field === field;
    const isSaving = isEditing && patchMut.isPending && patchMut.variables?.id === txn.id;
    const currentValue = txn.entities[field]?.value ?? "";

    if (isEditing) {
      return (
        <input
          ref={inputRef as any}
          type="text"
          value={inlineEdit.value}
          disabled={isSaving}
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => setInlineEdit({ ...inlineEdit, value: e.target.value })}
          onBlur={() => commitInline(txn)}
          onKeyDown={(e) => {
            if (e.key === "Enter") { e.preventDefault(); commitInline(txn); }
            else if (e.key === "Escape") { e.preventDefault(); setInlineEdit(null); }
          }}
          className={`${baseBox} border-primary bg-card text-foreground focus:outline-none focus:ring-1 focus:ring-primary`}
        />
      );
    }
    return (
      <span
        onClick={(e) => { e.stopPropagation(); startInline(txn, field); }}
        className={`${baseBox} border-transparent hover:bg-muted cursor-text truncate`}
        title={currentValue || "Click to edit"}
      >
        {currentValue || <span className="text-muted-foreground">-</span>}
        {isSaving && <Loader2 className="inline w-3 h-3 ml-1 animate-spin text-primary" />}
      </span>
    );
  };

  const renderCategoryCell = (txn: Transaction) => {
    const isEditing = inlineEdit?.txnId === txn.id && inlineEdit.field === "category";
    const isSaving = isEditing && patchMut.isPending && patchMut.variables?.id === txn.id;
    const currentValue = txn.entities.category?.value ?? "";

    if (isEditing) {
      return (
        <select
          ref={inputRef as any}
          value={inlineEdit.value}
          disabled={isSaving}
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => setInlineEdit({ ...inlineEdit, value: e.target.value })}
          onBlur={() => commitInline(txn)}
          onKeyDown={(e) => {
            if (e.key === "Escape") { e.preventDefault(); setInlineEdit(null); }
          }}
          className={`${baseBox} border-primary bg-card text-foreground focus:outline-none focus:ring-1 focus:ring-primary`}
        >
          {!CATEGORIES.includes(inlineEdit.value as any) && inlineEdit.value && (
            <option value={inlineEdit.value}>{inlineEdit.value}</option>
          )}
          {CATEGORIES.map((c) => (<option key={c} value={c}>{c}</option>))}
        </select>
      );
    }
    return (
      <span
        onClick={(e) => { e.stopPropagation(); startInline(txn, "category"); }}
        className={`${baseBox} border-transparent hover:bg-muted cursor-pointer truncate`}
        title="Click to change category"
      >
        {currentValue || <span className="text-muted-foreground">-</span>}
        {isSaving && <Loader2 className="inline w-3 h-3 ml-1 animate-spin text-primary" />}
      </span>
    );
  };

  const renderAmountCell = (txn: Transaction, side: "debit" | "credit") => {
    const matchesSide = (side === "debit" && txn.direction === "Dr") || (side === "credit" && txn.direction === "Cr");
    const isEditing = inlineEdit?.txnId === txn.id && inlineEdit.field === side;
    const isSaving = isEditing && patchMut.isPending && patchMut.variables?.id === txn.id;
    const shownValue = matchesSide ? txn.amount.toLocaleString('en-IN', { minimumFractionDigits: 2 }) : "";

    if (isEditing) {
      return (
        <input
          ref={inputRef as any}
          type="text"
          inputMode="decimal"
          value={inlineEdit.value}
          disabled={isSaving}
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => setInlineEdit({ ...inlineEdit, value: e.target.value })}
          onBlur={() => commitInline(txn)}
          onKeyDown={(e) => {
            if (e.key === "Enter") { e.preventDefault(); commitInline(txn); }
            else if (e.key === "Escape") { e.preventDefault(); setInlineEdit(null); }
          }}
          className={`${baseBox} border-primary bg-card text-foreground text-right tabular-nums focus:outline-none focus:ring-1 focus:ring-primary`}
        />
      );
    }
    return (
      <span
        onClick={(e) => { e.stopPropagation(); startInline(txn, side); }}
        className={`${baseBox} border-transparent hover:bg-muted cursor-text text-right tabular-nums`}
        title={matchesSide ? "Click to edit amount" : `Click to move to ${side}`}
      >
        {shownValue || <span className="text-muted-foreground/40">—</span>}
        {isSaving && <Loader2 className="inline w-3 h-3 ml-1 animate-spin text-primary" />}
      </span>
    );
  };

  // Group transactions by statement_id when viewing a single account so we
  // can show a separator between statements.
  const displayGroups: Array<{ statementId: string | null; transactions: Transaction[] }> = [];
  if (accountId) {
    let currentId: string | null = null;
    let currentGroup: Transaction[] = [];
    transactions.forEach((txn) => {
      if (txn.statement_id !== currentId) {
        if (currentGroup.length > 0) displayGroups.push({ statementId: currentId, transactions: currentGroup });
        currentId = txn.statement_id;
        currentGroup = [txn];
      } else {
        currentGroup.push(txn);
      }
    });
    if (currentGroup.length > 0) displayGroups.push({ statementId: currentId, transactions: currentGroup });
  } else {
    displayGroups.push({ statementId: null, transactions });
  }

  const visibleIds = transactions.map((t) => t.id);
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.has(id));
  const someVisibleSelected = !allVisibleSelected && visibleIds.some((id) => selectedIds.has(id));

  return (
    <div className="bg-card border border-border rounded-lg overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full" style={{ tableLayout: "fixed" }}>
          <colgroup>
            <col style={{ width: "2.5rem" }} />
            <col style={{ width: "2rem" }} />
            <col style={{ width: "6rem" }} />
            <col style={{ width: "3.5rem" }} />
            <col />
            <col style={{ width: "8rem" }} />
            <col style={{ width: "7rem" }} />
            <col style={{ width: "7rem" }} />
            <col style={{ width: "7rem" }} />
            <col style={{ width: "3.5rem" }} />
          </colgroup>
          <thead className="bg-background border-b border-border">
            <tr>
              <th className="px-3 py-3 text-center">
                <input
                  type="checkbox"
                  checked={allVisibleSelected}
                  ref={(el) => { if (el) el.indeterminate = someVisibleSelected; }}
                  onChange={() => onToggleSelectAll(visibleIds)}
                  className="rounded border-border"
                  title={allVisibleSelected ? "Deselect all visible" : "Select all visible"}
                />
              </th>
              <th className="px-2 py-3"></th>
              <th className="px-4 py-3 text-left text-xs font-medium text-foreground uppercase tracking-wider">Date</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-foreground uppercase tracking-wider">Ch</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-foreground uppercase tracking-wider">Counterparty</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-foreground uppercase tracking-wider">Category</th>
              <th className="px-4 py-3 text-right text-xs font-medium text-foreground uppercase tracking-wider">Debit</th>
              <th className="px-4 py-3 text-right text-xs font-medium text-foreground uppercase tracking-wider">Credit</th>
              <th className="px-4 py-3 text-right text-xs font-medium text-foreground uppercase tracking-wider">Balance</th>
              <th className="px-4 py-3 text-center text-xs font-medium text-foreground uppercase tracking-wider">Flag</th>
            </tr>
          </thead>
          <tbody>
            {displayGroups.map((group, groupIdx) => (
              <React.Fragment key={groupIdx}>
                {group.transactions.map((txn) => {
                  const isSelected = selectedIds.has(txn.id);
                  return (
                  <React.Fragment key={txn.id}>
                    <tr
                      onClick={() => toggleExpand(txn.id)}
                      onDoubleClick={(e) => { e.stopPropagation(); onEditTransaction(txn); }}
                      className={`border-b border-border/50 hover:bg-background cursor-pointer transition-colors ${
                        isSelected ? "bg-primary/5" : ""
                      }`}
                    >
                      <td className="px-3 py-3 text-center">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => {}}
                          onClick={(e) => { e.stopPropagation(); onToggleSelect(txn.id, e.shiftKey); }}
                          className="rounded border-border"
                        />
                      </td>
                      <td className="px-2 py-3">
                        <div className={`w-1 h-8 rounded ${txn.direction === 'Dr' ? 'bg-destructive' : 'bg-[color:var(--fl-emerald-500)]'}`} />
                      </td>
                      <td className="px-4 py-3 text-sm text-foreground whitespace-nowrap">
                        {new Date(txn.txn_date).toLocaleDateString('en-GB', {
                          day: '2-digit', month: '2-digit', year: '2-digit',
                        })}
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground truncate">
                        {txn.entities.channel?.value || '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-foreground">
                        {renderTextCell(txn, "counterparty")}
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">
                        {renderCategoryCell(txn)}
                      </td>
                      <td className="px-4 py-3 text-sm text-foreground">
                        {renderAmountCell(txn, "debit")}
                      </td>
                      <td className="px-4 py-3 text-sm text-foreground">
                        {renderAmountCell(txn, "credit")}
                      </td>
                      <td className="px-4 py-3 text-sm text-foreground text-right tabular-nums">
                        {txn.running_balance.toLocaleString('en-IN')}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <button
                          onClick={(e) => { e.stopPropagation(); toggleFlag(txn); }}
                          className="inline-flex items-center justify-center p-1 rounded hover:bg-muted"
                          title={txn.review_status === "flagged" ? "Click to unflag" : "Click to flag suspicious"}
                        >
                          {getFlagIcon(txn)}
                        </button>
                      </td>
                    </tr>

                    {expandedRows.has(txn.id) && (
                      <tr className="bg-background border-b border-border">
                        <td colSpan={10} className="px-4 py-4">
                          <div className="space-y-3">
                            <div>
                              <div className="text-xs font-medium text-muted-foreground mb-1">Raw OCR:</div>
                              <div className="text-sm text-foreground font-mono bg-card px-3 py-2 rounded border border-border">
                                {txn.raw_description}
                              </div>
                            </div>
                            <div>
                              <div className="text-xs font-medium text-muted-foreground mb-2">Entities:</div>
                              <div className="flex flex-wrap gap-2">
                                {Object.entries(txn.entities).map(([key, entity]) => (
                                  <span
                                    key={key}
                                    className={`px-2.5 py-1 rounded-full text-xs font-medium ${
                                      entity.confidence >= 0.8
                                        ? 'bg-[color:var(--fl-emerald-700)]/10 text-[color:var(--fl-emerald-500)]'
                                        : entity.confidence >= 0.5
                                        ? 'bg-amber-100 text-amber-800'
                                        : 'bg-destructive/10 text-destructive'
                                    }`}
                                  >
                                    {entity.value}
                                  </span>
                                ))}
                                {txn.tags.map((tag) => (
                                  <span key={tag} className="px-2.5 py-1 rounded-full text-xs font-medium bg-primary/10 text-primary">
                                    {tag}
                                  </span>
                                ))}
                              </div>
                            </div>
                            {txn.entities.ref_number && (
                              <div>
                                <span className="text-xs font-medium text-muted-foreground">Ref:</span>{' '}
                                <span className="text-sm text-foreground">{txn.entities.ref_number.value}</span>
                              </div>
                            )}
                            {txn.flags.length > 0 && (
                              <div>
                                <div className="text-xs font-medium text-muted-foreground mb-1">Flags:</div>
                                <div className="text-sm text-foreground space-y-1">
                                  {txn.flags.map((flag, idx) => (
                                    <div key={idx} className="flex items-center gap-2">
                                      <Flag className="w-3.5 h-3.5 text-amber-600 fill-amber-600" />
                                      <span>{flag.replace(/_/g, " ").toLowerCase()}</span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                            <div className="flex items-center gap-3 pt-2">
                              <button
                                onClick={(e) => { e.stopPropagation(); onEditTransaction(txn); }}
                                className="px-3 py-1.5 text-sm border border-border rounded hover:bg-card"
                              >
                                Edit…
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  patchMut.mutate({
                                    id: txn.id,
                                    patch: { review_status: txn.review_status === "reviewed" ? "unreviewed" : "reviewed" },
                                  });
                                }}
                                className="px-3 py-1.5 text-sm border border-border rounded hover:bg-card flex items-center gap-1.5"
                              >
                                <CheckCircle className="w-3.5 h-3.5" />
                                {txn.review_status === "reviewed" ? "Unmark reviewed" : "Mark reviewed"}
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  patchMut.mutate({
                                    id: txn.id,
                                    patch: { review_status: txn.review_status === "flagged" ? "unreviewed" : "flagged" },
                                  });
                                }}
                                className="px-3 py-1.5 text-sm border border-border rounded hover:bg-card flex items-center gap-1.5"
                              >
                                <Flag className="w-3.5 h-3.5" />
                                {txn.review_status === "flagged" ? "Unflag" : "Flag suspicious"}
                              </button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
                })}

                {groupIdx < displayGroups.length - 1 && accountId && (
                  <tr className="bg-muted border-y border-border">
                    <td colSpan={10} className="px-4 py-2 text-center text-xs text-muted-foreground">
                      ── statement {group.statementId} ends │ statement {displayGroups[groupIdx + 1].statementId} begins ──
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>

      <div className="px-4 py-3 bg-background border-t border-border text-xs text-muted-foreground">
        click row to peek · double-click for full editor · checkbox to select · click any editable cell to change
      </div>
    </div>
  );
}
