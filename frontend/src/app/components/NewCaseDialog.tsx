import { useState } from "react";
import { X, Loader2, AlertCircle } from "lucide-react";
import { useNavigate } from "react-router";
import { useCreateCase } from "../lib/queries";

interface NewCaseDialogProps {
  onClose: () => void;
}

export function NewCaseDialog({ onClose }: NewCaseDialogProps) {
  const [firNumber, setFirNumber] = useState("");
  const [title, setTitle] = useState("");
  const [officerName, setOfficerName] = useState("");
  const mut = useCreateCase();
  const navigate = useNavigate();

  const canSubmit =
    firNumber.trim().length > 0 &&
    title.trim().length > 0 &&
    officerName.trim().length > 0 &&
    !mut.isPending;

  const submit = async () => {
    if (!canSubmit) return;
    try {
      const created = await mut.mutateAsync({
        fir_number: firNumber.trim(),
        title: title.trim(),
        officer_name: officerName.trim(),
      });
      onClose();
      navigate(`/cases/${created.id}`);
    } catch {
      // mut.error renders below
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60]">
      <div className="bg-card rounded-lg shadow-xl w-full max-w-md mx-4">
        <div className="border-b border-border px-6 py-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">New case</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="px-6 py-5 space-y-3">
          <div>
            <label className="text-sm font-medium text-foreground block mb-1">
              FIR number <span className="text-destructive">*</span>
            </label>
            <input
              autoFocus
              value={firNumber}
              onChange={(e) => setFirNumber(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
              placeholder="FIR # 2026/AEC/0472"
              className="w-full px-3 py-2 border border-border rounded text-sm"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-foreground block mb-1">
              Title <span className="text-destructive">*</span>
            </label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
              placeholder="Bank fraud investigation — ABC Pvt Ltd"
              className="w-full px-3 py-2 border border-border rounded text-sm"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-foreground block mb-1">
              Officer name <span className="text-destructive">*</span>
            </label>
            <input
              value={officerName}
              onChange={(e) => setOfficerName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
              placeholder="Inspector R. Shyam"
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
            disabled={!canSubmit}
            className="px-4 py-2 bg-primary text-white rounded hover:bg-primary/90 flex items-center gap-2 disabled:opacity-50"
          >
            {mut.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
            Create case
          </button>
        </div>
      </div>
    </div>
  );
}
