import { useState } from "react";
import React from "react";
import { ChevronDown, ChevronUp, Flag, FileText, CheckCircle } from "lucide-react";
import type { Transaction } from "../data";
import { mockStatements } from "../data";

interface TransactionTableProps {
  transactions: Transaction[];
  accountId?: string;
  onEditTransaction: (transaction: Transaction) => void;
}

export function TransactionTable({ transactions, accountId, onEditTransaction }: TransactionTableProps) {
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  const toggleExpand = (txnId: string) => {
    const newExpanded = new Set(expandedRows);
    if (newExpanded.has(txnId)) {
      newExpanded.delete(txnId);
    } else {
      newExpanded.add(txnId);
    }
    setExpandedRows(newExpanded);
  };

  const getConfidenceColor = (confidence: string) => {
    switch (confidence) {
      case 'high':
        return 'text-[color:var(--fl-emerald-500)]';
      case 'medium':
        return 'text-amber-600';
      case 'low':
        return 'text-destructive';
      default:
        return 'text-muted-foreground';
    }
  };

  const getFlagIcon = (flags: string[]) => {
    if (flags.includes('SUM_CHECK_CONTRIBUTOR')) {
      return <Flag className="w-4 h-4 text-destructive fill-destructive" />;
    }
    if (flags.includes('NEEDS_REVIEW')) {
      return <Flag className="w-4 h-4 text-amber-600 fill-amber-600" />;
    }
    return null;
  };

  // Group transactions by statement
  const groupedTransactions: Array<{ statement: any; transactions: Transaction[] }> = [];
  let currentStatement: any = null;
  let currentGroup: Transaction[] = [];

  transactions.forEach((txn, idx) => {
    if (accountId) {
      const statement = mockStatements.find(s => s.id === txn.statement_id);
      if (statement !== currentStatement) {
        if (currentStatement && currentGroup.length > 0) {
          groupedTransactions.push({ statement: currentStatement, transactions: currentGroup });
        }
        currentStatement = statement;
        currentGroup = [txn];
      } else {
        currentGroup.push(txn);
      }
    } else {
      currentGroup.push(txn);
    }
  });

  if (currentGroup.length > 0) {
    groupedTransactions.push({ statement: currentStatement, transactions: currentGroup });
  }

  // If not filtered by account, just show all transactions
  const displayGroups = accountId ? groupedTransactions : [{ statement: null, transactions }];

  return (
    <div className="bg-card border border-border rounded-lg overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-background border-b border-border">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-foreground uppercase tracking-wider w-8"></th>
              <th className="px-4 py-3 text-left text-xs font-medium text-foreground uppercase tracking-wider">Date</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-foreground uppercase tracking-wider">Ch</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-foreground uppercase tracking-wider">Counterparty</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-foreground uppercase tracking-wider">Category</th>
              <th className="px-4 py-3 text-right text-xs font-medium text-foreground uppercase tracking-wider">Debit</th>
              <th className="px-4 py-3 text-right text-xs font-medium text-foreground uppercase tracking-wider">Credit</th>
              <th className="px-4 py-3 text-right text-xs font-medium text-foreground uppercase tracking-wider">Balance</th>
              <th className="px-4 py-3 text-center text-xs font-medium text-foreground uppercase tracking-wider w-10">Flag</th>
            </tr>
          </thead>
          <tbody>
            {displayGroups.map((group, groupIdx) => (
              <React.Fragment key={groupIdx}>
                {group.transactions.map((txn) => (
                  <React.Fragment key={txn.id}>
                    <tr
                      onClick={() => toggleExpand(txn.id)}
                      className="border-b border-border/50 hover:bg-background cursor-pointer transition-colors"
                    >
                      <td className="px-4 py-3">
                        <div className={`w-1 h-8 rounded ${txn.direction === 'Dr' ? 'bg-destructive' : 'bg-[color:var(--fl-emerald-500)]'}`} />
                      </td>
                      <td className="px-4 py-3 text-sm text-foreground whitespace-nowrap">
                        {new Date(txn.txn_date).toLocaleDateString('en-GB', {
                          day: '2-digit',
                          month: '2-digit',
                          year: '2-digit',
                        })}
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">
                        {txn.entities.channel?.value || '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-foreground">
                        {txn.entities.counterparty?.value || '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">
                        {txn.entities.category?.value || '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-foreground text-right tabular-nums">
                        {txn.direction === 'Dr' ? txn.amount.toLocaleString('en-IN', { minimumFractionDigits: 2 }) : ''}
                      </td>
                      <td className="px-4 py-3 text-sm text-foreground text-right tabular-nums">
                        {txn.direction === 'Cr' ? txn.amount.toLocaleString('en-IN', { minimumFractionDigits: 2 }) : ''}
                      </td>
                      <td className="px-4 py-3 text-sm text-foreground text-right tabular-nums">
                        {txn.running_balance.toLocaleString('en-IN')}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {getFlagIcon(txn.flags)}
                      </td>
                    </tr>

                    {expandedRows.has(txn.id) && (
                      <tr className="bg-background border-b border-border">
                        <td colSpan={9} className="px-4 py-4">
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
                                <button className="px-2.5 py-1 rounded-full text-xs font-medium border border-border text-muted-foreground hover:bg-muted">
                                  + tag
                                </button>
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
                                <div className="text-sm text-foreground">
                                  {txn.flags.map((flag, idx) => (
                                    <div key={idx} className="flex items-center gap-2">
                                      {flag === 'SUM_CHECK_CONTRIBUTOR' && (
                                        <>
                                          <Flag className="w-3.5 h-3.5 text-destructive fill-destructive" />
                                          <span>Sum-check contributor</span>
                                        </>
                                      )}
                                      {flag === 'NEEDS_REVIEW' && (
                                        <>
                                          <Flag className="w-3.5 h-3.5 text-amber-600 fill-amber-600" />
                                          <span>Needs review</span>
                                        </>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                            <div className="flex items-center gap-3 pt-2">
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onEditTransaction(txn);
                                }}
                                className="px-3 py-1.5 text-sm border border-border rounded hover:bg-card"
                              >
                                Edit…
                              </button>
                              <button className="px-3 py-1.5 text-sm border border-border rounded hover:bg-card flex items-center gap-1.5">
                                <FileText className="w-3.5 h-3.5" />
                                Open source PDF p.4
                              </button>
                              <button className="px-3 py-1.5 text-sm border border-border rounded hover:bg-card flex items-center gap-1.5">
                                <CheckCircle className="w-3.5 h-3.5" />
                                Mark reviewed
                              </button>
                              <button className="px-3 py-1.5 text-sm border border-border rounded hover:bg-card flex items-center gap-1.5">
                                <Flag className="w-3.5 h-3.5" />
                                Flag suspicious
                              </button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}

                {/* Inter-file separator */}
                {groupIdx < displayGroups.length - 1 && accountId && (
                  <tr className="bg-muted border-y border-border">
                    <td colSpan={9} className="px-4 py-2 text-center text-xs text-muted-foreground">
                      ── {new Date(group.statement.period_end).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })} statement ends │{' '}
                      {new Date(displayGroups[groupIdx + 1].statement.period_start).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })} statement begins ──
                      <button className="ml-3 text-primary hover:text-primary/80">⋯ file</button>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>

      <div className="px-4 py-3 bg-background border-t border-border text-xs text-muted-foreground">
        j/k navigate · click row to peek · double-click to edit · / search
      </div>
    </div>
  );
}