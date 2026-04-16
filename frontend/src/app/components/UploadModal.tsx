import { X, Check, Loader2, AlertCircle, Upload } from "lucide-react";
import { useState, useRef } from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import type { Person } from "../data";

interface UploadModalProps {
  onClose: () => void;
  caseId: string;
  personId?: string;
  persons: Person[];
}

interface UploadResult {
  bank_detected: string;
  statement: {
    id: string;
    account_id: string;
    source_file_name: string;
    period_start: string;
    period_end: string;
  };
  transaction_count: number;
}

type Status = "idle" | "uploading" | "done" | "error";

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

export function UploadModal({ onClose, caseId, personId, persons }: UploadModalProps) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [status, setStatus] = useState<Status>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedPerson, setSelectedPerson] = useState<string>(personId ?? persons[0]?.id ?? "");
  const inputRef = useRef<HTMLInputElement>(null);

  const handlePick = () => inputRef.current?.click();

  const handleSubmit = async () => {
    if (!file || !selectedPerson) return;
    setStatus("uploading");
    setError(null);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("person_id", selectedPerson);
    try {
      const res = await fetch(`${API_BASE}/api/cases/${caseId}/statements`, {
        method: "POST",
        body: fd,
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`${res.status} ${text.slice(0, 200)}`);
      }
      const data: UploadResult = await res.json();
      setResult(data);
      setStatus("done");
      qc.invalidateQueries({ queryKey: ["case", caseId] });
      qc.invalidateQueries({ queryKey: ["cases"] });
      qc.invalidateQueries({ queryKey: ["health"] });
    } catch (e: any) {
      setError(e.message || "Upload failed");
      setStatus("error");
    }
  };

  const handleOpenWorkbench = () => {
    navigate(`/cases/${caseId}/workbench?account=${result?.statement.account_id}`);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-card rounded-lg shadow-xl w-full max-w-2xl mx-4">
        <div className="border-b border-border px-6 py-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">
            {status === "idle" && "Upload bank statement"}
            {status === "uploading" && `Uploading ${file?.name}…`}
            {status === "done" && `Uploaded ${file?.name}`}
            {status === "error" && "Upload failed"}
          </h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-muted-foreground">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {status === "idle" && (
            <>
              <div className="grid grid-cols-3 gap-3 items-center">
                <label className="text-sm text-muted-foreground">Person:</label>
                <select
                  value={selectedPerson}
                  onChange={(e) => setSelectedPerson(e.target.value)}
                  className="col-span-2 px-3 py-2 border border-border rounded-lg text-sm"
                >
                  {persons.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </div>

              <div
                onClick={handlePick}
                className="border-2 border-dashed border-border rounded-lg p-10 text-center cursor-pointer hover:border-primary transition-colors"
              >
                <Upload className="w-10 h-10 mx-auto mb-3 text-muted-foreground" />
                <div className="text-foreground">
                  {file ? file.name : "Click to choose a PDF"}
                </div>
                {file && (
                  <div className="text-sm text-muted-foreground mt-1">
                    {(file.size / 1024).toFixed(0)} KB
                  </div>
                )}
                <input
                  ref={inputRef}
                  type="file"
                  accept="application/pdf"
                  className="hidden"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                />
              </div>
            </>
          )}

          {status === "uploading" && (
            <div className="flex items-center gap-3 py-6 text-foreground">
              <Loader2 className="w-5 h-5 animate-spin text-primary" />
              Parsing PDF and ingesting transactions…
            </div>
          )}

          {status === "done" && result && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-[color:var(--fl-emerald-500)]">
                <Check className="w-5 h-5" />
                <span className="text-foreground">Ingested {result.transaction_count} transactions</span>
              </div>
              <div className="bg-background rounded-lg p-4 text-sm space-y-1">
                <div><span className="text-muted-foreground">Bank detected:</span> <span className="font-medium text-foreground">{result.bank_detected}</span></div>
                <div><span className="text-muted-foreground">Statement ID:</span> <span className="font-mono text-foreground">{result.statement.id}</span></div>
                <div><span className="text-muted-foreground">Period:</span> <span className="text-foreground">{result.statement.period_start} → {result.statement.period_end}</span></div>
              </div>
            </div>
          )}

          {status === "error" && (
            <div className="flex items-start gap-2 text-destructive">
              <AlertCircle className="w-5 h-5 mt-0.5 flex-shrink-0" />
              <div className="text-sm">{error}</div>
            </div>
          )}
        </div>

        <div className="border-t border-border px-6 py-4 flex items-center justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 border border-border rounded-lg hover:bg-background">
            {status === "done" ? "Close" : "Cancel"}
          </button>
          {status === "idle" && (
            <button
              onClick={handleSubmit}
              disabled={!file || !selectedPerson}
              className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Upload
            </button>
          )}
          {status === "done" && (
            <button
              onClick={handleOpenWorkbench}
              className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90"
            >
              Open workbench
            </button>
          )}
          {status === "error" && (
            <button
              onClick={() => setStatus("idle")}
              className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90"
            >
              Try again
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
