import { useState } from "react";
import { X, Loader2, AlertCircle } from "lucide-react";
import { useCreatePerson } from "../lib/queries";
import type { Person } from "../data";

interface AddPersonDialogProps {
  caseId: string;
  onClose: () => void;
  onCreated?: (p: Person) => void;
  initialName?: string;
}

export function AddPersonDialog({ caseId, onClose, onCreated, initialName = "" }: AddPersonDialogProps) {
  const [name, setName] = useState(initialName);
  const [pan, setPan] = useState("");
  const [phone, setPhone] = useState("");
  const mut = useCreatePerson();

  const submit = async () => {
    if (!name.trim()) return;
    const body = {
      name: name.trim(),
      pan: pan.trim() || undefined,
      phone: phone.trim() || undefined,
    };
    try {
      const person = await mut.mutateAsync({ caseId, body });
      onCreated?.(person);
      onClose();
    } catch {
      // error is surfaced via mut.error
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60]">
      <div className="bg-card rounded-lg shadow-xl w-full max-w-md mx-4">
        <div className="border-b border-border px-6 py-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">Add person to case</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="px-6 py-5 space-y-3">
          <div>
            <label className="text-sm font-medium text-foreground block mb-1">
              Name <span className="text-destructive">*</span>
            </label>
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
              placeholder="Full name"
              className="w-full px-3 py-2 border border-border rounded text-sm"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-foreground block mb-1">PAN</label>
            <input
              value={pan}
              onChange={(e) => setPan(e.target.value.toUpperCase())}
              placeholder="ABCDE1234F (optional)"
              maxLength={10}
              className="w-full px-3 py-2 border border-border rounded text-sm font-mono"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-foreground block mb-1">Phone</label>
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+91… (optional)"
              className="w-full px-3 py-2 border border-border rounded text-sm"
            />
          </div>
          {mut.isError && (
            <div className="flex items-start gap-2 text-destructive bg-destructive/10 border border-destructive/30 rounded p-2 text-sm">
              <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <div>{String(mut.error)}</div>
            </div>
          )}
        </div>
        <div className="border-t border-border px-6 py-3 flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            disabled={mut.isPending}
            className="px-4 py-2 border border-border rounded hover:bg-background disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={mut.isPending || !name.trim()}
            className="px-4 py-2 bg-primary text-white rounded hover:bg-primary/90 flex items-center gap-2 disabled:opacity-50"
          >
            {mut.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
            Add person
          </button>
        </div>
      </div>
    </div>
  );
}
