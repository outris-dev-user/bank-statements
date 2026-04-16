import { X, Check, Loader2, AlertCircle, Upload, UserPlus, Sparkles } from "lucide-react";
import { useState, useRef } from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import type { Person } from "../data";
import { API_BASE, apiAuthHeaders } from "../lib/api";
import { AddPersonDialog } from "./AddPersonDialog";

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
  holder_name_guess: string | null;
  suggested_person_id: string | null;
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

export function UploadModal({ onClose, caseId, personId, persons }: UploadModalProps) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [status, setStatus] = useState<Status>("pick");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAddPerson, setShowAddPerson] = useState(false);
  const [autoMatched, setAutoMatched] = useState(false);

  // Explicit person choice. If a personId was passed in (user clicked a
  // person's Upload button) use it; otherwise leave blank and let detection
  // suggest one after the PDF is analysed.
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
    fd.append("case_id", caseId);
    try {
      const res = await fetch(`${API_BASE}/api/statements/preview`, {
        method: "POST",
        body: fd,
        headers: apiAuthHeaders(),
      });
      if (!res.ok) throw new Error(`${res.status} ${(await res.text()).slice(0, 200)}`);
      const data: PreviewResult = await res.json();
      setPreview(data);
      setBank(data.bank_label);
      setAccountType(data.account_type);
      setAccountNumber(data.account_number_guess ?? "");
      // If the user didn't pre-pick a person, accept the suggested match.
      if (!selectedPerson && data.suggested_person_id) {
        setSelectedPerson(data.suggested_person_id);
        setAutoMatched(true);
      } else {
        setAutoMatched(false);
      }
      // Holder name — prefer detected value, fall back to person's name.
      setHolderName(
        data.holder_name_guess ||
        persons.find((p) => p.id === (selectedPerson || data.suggested_person_id))?.name ||
        "",
      );
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

  const onPersonCreated = (p: Person) => {
    // A newly-created person doesn't show up in `persons` (that prop is
    // stale until react-query refetches the case), but we can still select
    // it by id — the backend knows about it.
    setSelectedPerson(p.id);
    setAutoMatched(false);
    if (!holderName && preview?.holder_name_guess) setHolderName(preview.holder_name_guess);
    else if (!holderName) setHolderName(p.name);
    qc.invalidateQueries({ queryKey: ["case", caseId] });
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
      const res = await fetch(`${API_BASE}/api/cases/${caseId}/statements`, {
        method: "POST",
        body: fd,
        headers: apiAuthHeaders(),
      });
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

  // Selected person may be a freshly-created one not yet in `persons` —
  // derive displayed name from the list first, fall back to the preview
  // holder value.
  const selectedPersonName = persons.find((p) => p.id === selectedPerson)?.name;
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
          {/* Step 1: file picker. Person selection is resolved below after preview. */}
          {status === "pick" && (
            <>
              <p className="text-sm text-muted-foreground">
                Drop a PDF in and we'll detect the bank, account, and holder name. You'll confirm who it belongs to before it's saved.
              </p>
              <div
                onClick={handlePick}
                className="border-2 border-dashed border-border hover:border-primary rounded-lg p-10 text-center cursor-pointer transition-colors"
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
            </>
          )}

          {status === "previewing" && (
            <div className="flex items-center gap-3 py-6 text-foreground">
              <Loader2 className="w-5 h-5 animate-spin text-primary" />
              Detecting bank, account, and holder name…
            </div>
          )}

          {/* Step 2: preview → person assignment + confirm */}
          {status === "preview_ready" && preview && (
            <div className="space-y-4">
              <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3 text-sm">
                <div className="flex items-center gap-2 text-emerald-900">
                  <Check className="w-4 h-4" />
                  <span className="font-medium">{preview.transaction_count} transactions extracted</span>
                </div>
                <div className="text-xs text-emerald-900/80 mt-0.5">
                  Bank detected: <span className="font-mono">{preview.bank_detected}</span> · Period {preview.period_start} → {preview.period_end}
                </div>
                {preview.holder_name_guess && (
                  <div className="text-xs text-emerald-900/80 mt-0.5">
                    Holder detected: <span className="font-medium">{preview.holder_name_guess}</span>
                  </div>
                )}
              </div>

              {/* Person assignment */}
              <div className="bg-background border border-border rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium text-foreground">
                    Attach to person <span className="text-destructive">*</span>
                  </label>
                  <button
                    onClick={() => setShowAddPerson(true)}
                    className="text-xs px-2 py-1 text-primary hover:bg-primary/10 rounded flex items-center gap-1"
                  >
                    <UserPlus className="w-3.5 h-3.5" />
                    Add new person
                  </button>
                </div>
                <select
                  value={selectedPerson}
                  onChange={(e) => { setSelectedPerson(e.target.value); setAutoMatched(false); }}
                  className={`w-full px-3 py-2 border rounded text-sm bg-card ${
                    selectedPerson ? "border-border" : "border-amber-400 bg-amber-50"
                  }`}
                >
                  <option value="">— Pick a person —</option>
                  {persons.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                  {/* If the user just created a new person, they won't be in
                      `persons` yet (props are stale until the case refetches).
                      Show the freshly-selected id as a placeholder option. */}
                  {selectedPerson && !persons.find((p) => p.id === selectedPerson) && (
                    <option value={selectedPerson}>
                      {selectedPersonName ?? `(newly created — ${selectedPerson})`}
                    </option>
                  )}
                </select>
                {autoMatched && selectedPerson && (
                  <div className="text-xs text-primary mt-1.5 flex items-center gap-1">
                    <Sparkles className="w-3.5 h-3.5" />
                    Auto-matched by holder name. Change if wrong.
                  </div>
                )}
                {!selectedPerson && preview.holder_name_guess && (
                  <div className="text-xs text-amber-700 mt-1.5 flex items-center gap-1">
                    <AlertCircle className="w-3.5 h-3.5" />
                    No existing person matches "{preview.holder_name_guess}" — pick one, or add them as a new person.
                  </div>
                )}
                {!selectedPerson && !preview.holder_name_guess && (
                  <div className="text-xs text-amber-700 mt-1.5 flex items-center gap-1">
                    <AlertCircle className="w-3.5 h-3.5" />
                    Couldn't detect the holder name from this PDF — pick a person manually.
                  </div>
                )}
              </div>

              {/* Account details */}
              <div className="bg-background border border-border rounded-lg p-4 space-y-3">
                <div className="text-xs uppercase tracking-wider text-muted-foreground">Account details</div>
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
                        Couldn't auto-detect. Type the last 4 digits.
                      </div>
                    )}
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground block mb-1">Holder name on statement</label>
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

      {showAddPerson && (
        <AddPersonDialog
          caseId={caseId}
          initialName={preview?.holder_name_guess ?? ""}
          onClose={() => setShowAddPerson(false)}
          onCreated={onPersonCreated}
        />
      )}
    </div>
  );
}
