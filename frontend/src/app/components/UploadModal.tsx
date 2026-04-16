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

interface PreviewResult {
  bank_detected: string;
  bank_label: string;
  account_type: string;
  account_number_guess: string | null;
  period_start: string;
  period_end: string;
  transaction_count: number;
  filename: string;
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

type Status = "pick" | "previewing" | "preview_ready" | "uploading" | "done" | "error";

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

export function UploadModal({ onClose, caseId, personId, persons }: UploadModalProps) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [status, setStatus] = useState<Status>("pick");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Explicit person choice — required. "" means "not chosen yet", and we
  // default to the `personId` prop only if it was passed (i.e. the user
  // clicked a specific person's Upload button). Otherwise force them to pick.
  const [selectedPerson, setSelectedPerson] = useState<string>(personId ?? "");

  // Detected values the user can override before committing
  const [bank, setBank] = useState<string>("");
  const [accountType, setAccountType] = useState<string>("");
  const [accountNumber, setAccountNumber] = useState<string>("");
  const [holderName, setHolderName] = useState<string>("");

  const inputRef = useRef<HTMLInputElement>(null);
  const handlePick = () => inputRef.current?.click();

  const runPreview = async (f: File) => {
    setStatus("previewing");
    setError(null);
    const fd = new FormData();
    fd.append("file", f);
    try {
      const res = await fetch(`${API_BASE}/api/statements/preview`, { method: "POST", body: fd });
      if (!res.ok) throw new Error(`${res.status} ${(await res.text()).slice(0, 200)}`);
      const data: PreviewResult = await res.json();
      setPreview(data);
      setBank(data.bank_label);
      setAccountType(data.account_type);
      setAccountNumber(data.account_number_guess ?? "");
      setHolderName(persons.find((p) => p.id === selectedPerson)?.name ?? "");
      setStatus("preview_ready");
    } catch (e: any) {
      setError(e.message || "Preview failed");
      setStatus("error");
    }
  };

  const onFilePicked = async (f: File | null) => {
    setFile(f);
    if (f) await runPreview(f);
  };

  const commitUpload = async () => {
    if (!file || !selectedPerson) return;
    if (!accountNumber.trim()) {
      setError("Account number is required — type the last 4 digits at least.");
      setStatus("error");
      return;
    }
    setStatus("uploading");
    setError(null);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("person_id", selectedPerson);
    fd.append("bank", bank);
    fd.append("account_type", accountType);
    fd.append("account_number", accountNumber.trim());
    fd.append("holder_name", holderName || "Unknown");
    try {
      const res = await fetch(`${API_BASE}/api/cases/${caseId}/statements`, { method: "POST", body: fd });
      if (!res.ok) throw new Error(`${res.status} ${(await res.text()).slice(0, 200)}`);
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

  const personName = persons.find((p) => p.id === selectedPerson)?.name;
  const canCommit = !!file && !!selectedPerson && !!accountNumber.trim() && status === "preview_ready";

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-card rounded-lg shadow-xl w-full max-w-2xl mx-4 max-h-[90vh] overflow-hidden flex flex-col">
        <div className="border-b border-border px-6 py-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">
            {status === "pick" && "Upload bank statement"}
            {status === "previewing" && "Analysing PDF…"}
            {status === "preview_ready" && "Confirm before upload"}
            {status === "uploading" && `Uploading ${file?.name}…`}
            {status === "done" && `Uploaded ${file?.name}`}
            {status === "error" && "Upload failed"}
          </h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-muted-foreground">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
          {/* Step 1: who is this for? Always visible. */}
          <div>
            <label className="text-sm font-medium text-foreground block mb-1">
              Person <span className="text-destructive">*</span>
            </label>
            <select
              value={selectedPerson}
              onChange={(e) => setSelectedPerson(e.target.value)}
              className={`w-full px-3 py-2 border rounded-lg text-sm bg-card ${
                selectedPerson ? "border-border" : "border-amber-400 bg-amber-50"
              }`}
            >
              <option value="">— Pick a person —</option>
              {persons.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
            {!selectedPerson && (
              <div className="text-xs text-amber-700 mt-1 flex items-center gap-1">
                <AlertCircle className="w-3.5 h-3.5" />
                Statements are attached to a person's accounts — pick the right one.
              </div>
            )}
          </div>

          {/* Step 2: file picker */}
          {status === "pick" && (
            <div
              onClick={selectedPerson ? handlePick : undefined}
              className={`border-2 border-dashed rounded-lg p-10 text-center transition-colors ${
                selectedPerson
                  ? "border-border hover:border-primary cursor-pointer"
                  : "border-border/50 opacity-50 cursor-not-allowed"
              }`}
              title={selectedPerson ? "" : "Pick a person first"}
            >
              <Upload className="w-10 h-10 mx-auto mb-3 text-muted-foreground" />
              <div className="text-foreground">{file ? file.name : "Click to choose a PDF"}</div>
              {file && <div className="text-sm text-muted-foreground mt-1">{(file.size / 1024).toFixed(0)} KB</div>}
              <input
                ref={inputRef}
                type="file"
                accept="application/pdf"
                className="hidden"
                onChange={(e) => onFilePicked(e.target.files?.[0] ?? null)}
              />
            </div>
          )}

          {/* Step 3: analyse */}
          {status === "previewing" && (
            <div className="flex items-center gap-3 py-6 text-foreground">
              <Loader2 className="w-5 h-5 animate-spin text-primary" />
              Detecting bank and extracting transactions…
            </div>
          )}

          {/* Step 4: preview → confirm */}
          {status === "preview_ready" && preview && (
            <div className="space-y-3">
              <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3 text-sm">
                <div className="flex items-center gap-2 text-emerald-900">
                  <Check className="w-4 h-4" />
                  <span className="font-medium">{preview.transaction_count} transactions extracted</span>
                </div>
                <div className="text-xs text-emerald-900/80 mt-0.5">
                  Bank detected: <span className="font-mono">{preview.bank_detected}</span> · Period {preview.period_start} → {preview.period_end}
                </div>
              </div>

              <div className="bg-background border border-border rounded-lg p-4 space-y-3">
                <div className="text-xs uppercase tracking-wider text-muted-foreground">Will add to</div>
                <div className="text-sm font-medium text-foreground">
                  {personName || "— no person selected —"}
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs text-muted-foreground block mb-1">Bank</label>
                    <input
                      value={bank}
                      onChange={(e) => setBank(e.target.value)}
                      className="w-full px-3 py-2 border border-border rounded text-sm"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground block mb-1">Account type</label>
                    <select
                      value={accountType}
                      onChange={(e) => setAccountType(e.target.value)}
                      className="w-full px-3 py-2 border border-border rounded text-sm bg-card"
                    >
                      <option value="SA">SA — Savings</option>
                      <option value="CA">CA — Current</option>
                      <option value="CC">CC — Credit card</option>
                      <option value="OD">OD — Overdraft</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground block mb-1">
                      Account number <span className="text-destructive">*</span>
                    </label>
                    <input
                      value={accountNumber}
                      onChange={(e) => setAccountNumber(e.target.value)}
                      placeholder="e.g. ****1234"
                      className={`w-full px-3 py-2 border rounded text-sm ${
                        accountNumber.trim() ? "border-border" : "border-amber-400 bg-amber-50"
                      }`}
                    />
                    {!preview.account_number_guess && (
                      <div className="text-xs text-amber-700 mt-1">
                        Couldn't auto-detect. Type the last 4 digits so this account can be identified.
                      </div>
                    )}
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground block mb-1">Holder name</label>
                    <input
                      value={holderName}
                      onChange={(e) => setHolderName(e.target.value)}
                      className="w-full px-3 py-2 border border-border rounded text-sm"
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {status === "uploading" && (
            <div className="flex items-center gap-3 py-6 text-foreground">
              <Loader2 className="w-5 h-5 animate-spin text-primary" />
              Persisting transactions…
            </div>
          )}

          {status === "done" && result && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-[color:var(--fl-emerald-500)]">
                <Check className="w-5 h-5" />
                <span className="text-foreground">Ingested {result.transaction_count} transactions</span>
              </div>
              <div className="bg-background rounded-lg p-4 text-sm space-y-1">
                <div><span className="text-muted-foreground">Statement ID:</span> <span className="font-mono text-foreground">{result.statement.id}</span></div>
                <div><span className="text-muted-foreground">Account ID:</span> <span className="font-mono text-foreground">{result.statement.account_id}</span></div>
                <div><span className="text-muted-foreground">Period:</span> <span className="text-foreground">{result.statement.period_start} → {result.statement.period_end}</span></div>
              </div>
            </div>
          )}

          {status === "error" && (
            <div className="flex items-start gap-2 text-destructive bg-destructive/10 border border-destructive/30 rounded-lg p-3">
              <AlertCircle className="w-5 h-5 mt-0.5 flex-shrink-0" />
              <div className="text-sm">{error}</div>
            </div>
          )}
        </div>

        <div className="border-t border-border px-6 py-4 flex items-center justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 border border-border rounded-lg hover:bg-background">
            {status === "done" ? "Close" : "Cancel"}
          </button>
          {status === "preview_ready" && (
            <button
              onClick={commitUpload}
              disabled={!canCommit}
              className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Confirm &amp; upload
            </button>
          )}
          {status === "done" && (
            <button onClick={handleOpenWorkbench} className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90">
              Open workbench
            </button>
          )}
          {status === "error" && (
            <button
              onClick={() => { setStatus(file ? "preview_ready" : "pick"); setError(null); }}
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
