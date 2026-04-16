import { X, FileText, Info, Loader2, AlertCircle } from "lucide-react";
import type { Transaction } from "../data";
import { useState } from "react";
import { usePatchTransaction, useTransactionAudit, useEntities, useLinkEntity } from "../lib/queries";
import { statementPdfUrl } from "../lib/api";

interface EditDrawerProps {
  transaction: Transaction;
  onClose: () => void;
  caseId?: string;
}

export function EditDrawer({ transaction, onClose, caseId }: EditDrawerProps) {
  const [entities, setEntities] = useState(transaction.entities);
  const [tags, setTags] = useState(transaction.tags);
  const [amount, setAmount] = useState(transaction.amount.toString());
  const [date, setDate] = useState(transaction.txn_date);

  const patchMut = usePatchTransaction();
  const { data: auditEvents } = useTransactionAudit(transaction.id);
  const { data: caseEntities } = useEntities(caseId);
  const linkMut = useLinkEntity();

  // Fuzzy-find entities that already mention this counterparty (exact name
  // or alias). If we find one, offer a one-click link.
  const cpValue = entities.counterparty?.value?.trim() ?? "";
  const cpLower = cpValue.toLowerCase();
  const suggestion = caseEntities?.find((e) => {
    if (!cpLower) return false;
    if (e.name.toLowerCase() === cpLower) return true;
    if (e.aliases.some((a) => a.toLowerCase() === cpLower)) return true;
    return false;
  });

  const handleSave = () => {
    patchMut.mutate(
      {
        id: transaction.id,
        patch: {
          entities,
          tags,
          amount: Number(amount) || transaction.amount,
          txn_date: date,
        },
      },
      { onSuccess: () => onClose() },
    );
  };

  return (
    <div className="fixed inset-y-0 right-0 w-[500px] bg-card shadow-2xl border-l border-border z-50 flex flex-col">
      {/* Header */}
      <div className="border-b border-border px-6 py-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-foreground">Edit transaction</h2>
        <button onClick={onClose} className="text-muted-foreground hover:text-muted-foreground">
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
        {/* Transaction summary */}
        <div className="pb-4 border-b border-border">
          <div className="text-sm text-muted-foreground mb-1">
            {new Date(transaction.txn_date).toLocaleDateString('en-GB')} · {transaction.entities.channel?.value || 'N/A'} ·{' '}
            {transaction.direction} ₹{transaction.amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </div>
          <div className="text-sm text-muted-foreground">
            Balance after: ₹{transaction.running_balance.toLocaleString('en-IN')}
          </div>
        </div>

        {/* Raw OCR */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-medium text-foreground">Raw OCR</label>
            <a
              href={statementPdfUrl(transaction.statement_id)}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-primary hover:text-primary/80 flex items-center gap-1"
            >
              <FileText className="w-3.5 h-3.5" />
              Open source PDF
            </a>
          </div>
          <div className="px-3 py-2 bg-background border border-border rounded-lg text-sm text-foreground font-mono">
            {transaction.raw_description}
          </div>
        </div>

        {/* Entities */}
        <div>
          <label className="text-sm font-medium text-foreground block mb-3">Entities (key-value)</label>
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-3 items-center">
              <label className="text-sm text-muted-foreground">Channel:</label>
              <select
                value={entities.channel?.value || ''}
                onChange={(e) =>
                  setEntities({
                    ...entities,
                    channel: { value: e.target.value, source: 'user_edited', confidence: 1.0 },
                  })
                }
                className="col-span-2 px-3 py-2 border border-border rounded-lg text-sm"
              >
                <option value="UPI">UPI</option>
                <option value="NEFT">NEFT</option>
                <option value="IMPS">IMPS</option>
                <option value="RTGS">RTGS</option>
                <option value="ATM">ATM</option>
                <option value="POS">POS</option>
                <option value="Cheque">Cheque</option>
                <option value="Cash">Cash</option>
                <option value="Other">Other</option>
              </select>
            </div>

            <div className="grid grid-cols-3 gap-3 items-center">
              <label className="text-sm text-muted-foreground">Counterparty:</label>
              <input
                type="text"
                value={entities.counterparty?.value || ''}
                onChange={(e) =>
                  setEntities({
                    ...entities,
                    counterparty: { value: e.target.value, source: 'user_edited', confidence: 1.0 },
                  })
                }
                className="col-span-2 px-3 py-2 border border-border rounded-lg text-sm"
              />
            </div>

            <div className="grid grid-cols-3 gap-3 items-center">
              <label className="text-sm text-muted-foreground">Category:</label>
              <select
                value={entities.category?.value || ''}
                onChange={(e) =>
                  setEntities({
                    ...entities,
                    category: { value: e.target.value, source: 'user_edited', confidence: 1.0 },
                  })
                }
                className="col-span-2 px-3 py-2 border border-border rounded-lg text-sm"
              >
                <option value="Food">Food</option>
                <option value="Transfer">Transfer</option>
                <option value="Salary">Salary</option>
                <option value="Rent">Rent</option>
                <option value="Shopping">Shopping</option>
                <option value="Finance">Finance</option>
                <option value="Cash">Cash</option>
                <option value="Rewards">Rewards</option>
                <option value="Other">Other</option>
              </select>
            </div>

            {entities.ref_number && (
              <div className="grid grid-cols-3 gap-3 items-center">
                <label className="text-sm text-muted-foreground">Ref number:</label>
                <input
                  type="text"
                  value={entities.ref_number.value}
                  disabled
                  className="col-span-2 px-3 py-2 border border-border rounded-lg text-sm bg-background text-muted-foreground"
                />
              </div>
            )}

            <div className="grid grid-cols-3 gap-3 items-start">
              <label className="text-sm text-muted-foreground pt-2">Tags:</label>
              <div className="col-span-2 flex flex-wrap gap-2">
                {tags.map((tag) => (
                  <span
                    key={tag}
                    className="px-2.5 py-1 rounded-full text-xs font-medium bg-primary/10 text-primary flex items-center gap-1"
                  >
                    {tag}
                    <button
                      onClick={() => setTags(tags.filter((t) => t !== tag))}
                      className="hover:text-primary/90"
                    >
                      ×
                    </button>
                  </span>
                ))}
                <button className="px-2.5 py-1 rounded-full text-xs font-medium border border-border text-muted-foreground hover:bg-muted">
                  + tag
                </button>
              </div>
            </div>

            <button className="text-sm text-primary hover:text-primary/80">+ Add custom entity</button>
          </div>
        </div>

        {/* Linked entity (live, from entity resolver) */}
        <div>
          <label className="text-sm font-medium text-foreground block mb-2">Linked entity</label>
          {suggestion ? (
            <div className="bg-primary/5 border border-primary/20 rounded-lg p-3 text-sm space-y-1">
              <div className="flex items-start gap-2">
                <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0 text-primary" />
                <div className="flex-1">
                  <div className="text-foreground">
                    Matches entity <span className="font-medium">{suggestion.name}</span>
                    <span className="text-muted-foreground"> · {suggestion.txn_count} txns</span>
                  </div>
                  {suggestion.aliases.length > 0 && (
                    <div className="text-xs text-muted-foreground mt-0.5">
                      aliases: {suggestion.aliases.slice(0, 3).join(", ")}
                      {suggestion.aliases.length > 3 && ` +${suggestion.aliases.length - 3}`}
                    </div>
                  )}
                </div>
              </div>
              <button
                onClick={() => linkMut.mutate({ txnId: transaction.id, entityId: suggestion.id })}
                disabled={linkMut.isPending}
                className="text-xs text-primary hover:text-primary/80 font-medium ml-5"
              >
                {linkMut.isPending ? "Linking…" : linkMut.isSuccess ? "Linked ✓" : "Link this transaction →"}
              </button>
            </div>
          ) : cpValue ? (
            <div className="text-xs text-muted-foreground">
              No existing entity matches "{cpValue}". Use the Entities tab to resolve manually.
            </div>
          ) : (
            <div className="text-xs text-muted-foreground">Set a counterparty to see entity matches.</div>
          )}
        </div>

        {/* Amount & date */}
        <div>
          <label className="text-sm font-medium text-foreground block mb-3">Amount & date</label>
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-3 items-center">
              <label className="text-sm text-muted-foreground">{transaction.direction === 'Dr' ? 'Debit' : 'Credit'}:</label>
              <input
                type="text"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="col-span-2 px-3 py-2 border border-border rounded-lg text-sm"
              />
            </div>
            <div className="grid grid-cols-3 gap-3 items-center">
              <label className="text-sm text-muted-foreground">Date:</label>
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="col-span-2 px-3 py-2 border border-border rounded-lg text-sm"
              />
            </div>
            <div className="text-xs text-muted-foreground flex items-start gap-1.5">
              <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
              Editing these recomputes balance
            </div>
          </div>
        </div>

        {/* Notes */}
        <div>
          <label className="text-sm font-medium text-foreground block mb-2">Notes</label>
          <textarea
            className="w-full px-3 py-2 border border-border rounded-lg text-sm resize-none"
            rows={3}
            placeholder="Add notes..."
          />
        </div>

        {/* Audit trail */}
        <div>
          <label className="text-sm font-medium text-foreground block mb-2">Audit trail</label>
          {auditEvents === undefined ? (
            <div className="text-xs text-muted-foreground">Loading…</div>
          ) : auditEvents.length === 0 ? (
            <div className="text-xs text-muted-foreground">No edits yet.</div>
          ) : (
            <div className="space-y-1.5 max-h-40 overflow-y-auto pr-1">
              {auditEvents.map((ev, idx) => (
                <div key={idx} className="text-xs border-l-2 border-border pl-2 py-0.5">
                  <div className="flex items-center justify-between text-muted-foreground">
                    <span>
                      <span className="font-mono text-foreground">{ev.field}</span> · by <span className="text-foreground">{ev.by}</span>
                    </span>
                    <span>{new Date(ev.at).toLocaleString("en-GB", { hour12: false })}</span>
                  </div>
                  <div className="text-muted-foreground mt-0.5">
                    <span className="line-through opacity-70">{String(ev.old).slice(0, 80)}</span>
                    {" → "}
                    <span className="text-foreground">{String(ev.new).slice(0, 80)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="border-t border-border px-6 py-4 flex items-center justify-end gap-3">
        {patchMut.isError && (
          <div className="flex items-center gap-1.5 text-sm text-destructive mr-auto">
            <AlertCircle className="w-4 h-4" />
            {String(patchMut.error)}
          </div>
        )}
        <button
          onClick={onClose}
          disabled={patchMut.isPending}
          className="px-4 py-2 border border-border rounded-lg hover:bg-background disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          onClick={handleSave}
          disabled={patchMut.isPending}
          className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 flex items-center gap-2 disabled:opacity-50"
        >
          {patchMut.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
          Save
        </button>
      </div>
    </div>
  );
}
