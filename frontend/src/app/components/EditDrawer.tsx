import { X, FileText, Info } from "lucide-react";
import type { Transaction } from "../data/mockData";
import { useState } from "react";

interface EditDrawerProps {
  transaction: Transaction;
  onClose: () => void;
}

export function EditDrawer({ transaction, onClose }: EditDrawerProps) {
  const [entities, setEntities] = useState(transaction.entities);
  const [tags, setTags] = useState(transaction.tags);
  const [amount, setAmount] = useState(transaction.amount.toString());
  const [date, setDate] = useState(transaction.txn_date);

  const handleSave = () => {
    // In a real app, this would save to backend
    console.log('Saving transaction:', { entities, tags, amount, date });
    onClose();
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
            <button className="text-xs text-primary hover:text-primary/80 flex items-center gap-1">
              <FileText className="w-3.5 h-3.5" />
              Source PDF p.4
            </button>
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

        {/* Linked entity */}
        <div>
          <label className="text-sm font-medium text-foreground block mb-3">Linked person / entity</label>
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm">
              <input type="radio" name="link" defaultChecked className="text-primary" />
              <span>Not linked</span>
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="radio" name="link" className="text-primary" />
              <span>Link to existing…</span>
            </label>
            {entities.counterparty && (
              <div className="ml-6 text-xs text-muted-foreground flex items-start gap-1.5">
                <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                <div>
                  "{entities.counterparty.value}" appears in 3 other rows
                  <button className="block text-primary hover:text-primary/80 mt-1">
                    Link all 4 to same entity
                  </button>
                </div>
              </div>
            )}
            <label className="flex items-center gap-2 text-sm">
              <input type="radio" name="link" className="text-primary" />
              <span>Create new counterparty entity</span>
            </label>
          </div>
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

        {/* Audit */}
        <div className="text-xs text-muted-foreground">
          <div>Audit: extracted {new Date(transaction.txn_date).toLocaleDateString('en-GB')} 12:04</div>
          <div>Last edited: never</div>
        </div>
      </div>

      {/* Footer */}
      <div className="border-t border-border px-6 py-4 flex items-center justify-end gap-3">
        <button onClick={onClose} className="px-4 py-2 border border-border rounded-lg hover:bg-background">
          Cancel
        </button>
        <button onClick={handleSave} className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90">
          Save
        </button>
      </div>
    </div>
  );
}
