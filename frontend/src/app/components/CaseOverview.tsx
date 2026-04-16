import { Link, useParams, useNavigate } from "react-router";
import { ChevronLeft, User, Upload, Plus, CheckCircle, AlertTriangle, Trash2, FileText, Loader2 } from "lucide-react";
import { useState } from "react";
import { UploadModal } from "./UploadModal";
import { useCase, useDeleteStatement } from "../lib/queries";
import { statementPdfUrl } from "../lib/api";

export function CaseOverview() {
  const { caseId } = useParams();
  const navigate = useNavigate();
  const [showUpload, setShowUpload] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [uploadPersonId, setUploadPersonId] = useState<string | undefined>(undefined);

  const { data: detail, isLoading, error } = useCase(caseId);
  const deleteMut = useDeleteStatement();

  if (isLoading) return <div className="p-8 text-muted-foreground">Loading…</div>;
  if (error) return <div className="p-8 text-destructive">Failed to load: {String(error)}</div>;
  if (!detail) return <div>Case not found</div>;

  const { case: caseItem, persons, accounts, statements } = detail;

  const statementsForAccount = (accountId: string) =>
    statements.filter((s) => s.account_id === accountId);

  const handleDelete = (statementId: string, fileName: string) => {
    if (!confirm(`Delete statement "${fileName}"? This removes its transactions, audit events, and entity links. This cannot be undone.`)) return;
    deleteMut.mutate(statementId);
  };

  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setDragOver(true); };
  const handleDragLeave = () => setDragOver(false);
  const handleDrop = (e: React.DragEvent) => { e.preventDefault(); setDragOver(false); setShowUpload(true); };

  return (
    <div className="min-h-screen bg-background">
      <header className="bg-card border-b border-border px-6 py-4">
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <div className="flex items-center gap-4">
            <Link to="/" className="text-muted-foreground hover:text-foreground">
              <ChevronLeft className="w-5 h-5" />
            </Link>
            <h1 className="text-xl font-semibold text-foreground">{caseItem.fir_number}</h1>
          </div>
          <button className="w-9 h-9 rounded-full bg-muted hover:bg-accent flex items-center justify-center">
            <User className="w-4 h-4 text-foreground" />
          </button>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        <div className="mb-8">
          <h2 className="text-2xl font-semibold text-foreground mb-1">{caseItem.title.split(' — ')[0]} investigation</h2>
          <p className="text-muted-foreground">Officer: {caseItem.officer_name}</p>
        </div>

        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-foreground">Persons in this case</h3>
            <button className="px-4 py-2 border border-border rounded-lg hover:bg-background flex items-center gap-2 text-sm">
              <Plus className="w-4 h-4" />
              Add person
            </button>
          </div>

          <div className="space-y-6">
            {persons.map((person) => {
              const personAccounts = accounts.filter((a) => a.person_id === person.id);
              return (
                <div key={person.id} className="bg-card rounded-lg border border-border p-6">
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <User className="w-5 h-5 text-muted-foreground" />
                      <h4 className="font-semibold text-foreground">{person.name}</h4>
                    </div>
                    <button
                      onClick={() => { setUploadPersonId(person.id); setShowUpload(true); }}
                      className="px-4 py-2 border border-border rounded-lg hover:bg-background flex items-center gap-2 text-sm"
                    >
                      <Upload className="w-4 h-4" />
                      Upload statement
                    </button>
                  </div>

                  {personAccounts.length > 0 ? (
                    <div className="space-y-3">
                      {personAccounts.map((account) => {
                        const accountStatements = statementsForAccount(account.id);
                        return (
                          <div key={account.id} className="bg-background rounded-lg">
                            <div
                              onClick={() => navigate(`/cases/${caseId}/workbench?account=${account.id}`)}
                              className="flex items-center justify-between p-3 cursor-pointer hover:bg-muted transition-colors rounded-t-lg"
                            >
                              <div className="flex items-center gap-3">
                                <span className="text-xl">🏦</span>
                                <div>
                                  <div className="font-medium text-foreground">
                                    {account.bank} A/C {account.account_number} ({account.account_type})
                                  </div>
                                  {account.holder_name && account.holder_name !== "Unknown" && (
                                    <div className="text-xs text-muted-foreground">holder: {account.holder_name}</div>
                                  )}
                                </div>
                              </div>
                              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                {account.has_warnings ? (
                                  <AlertTriangle className="w-4 h-4 text-amber-500" />
                                ) : (
                                  <CheckCircle className="w-4 h-4 text-green-500" />
                                )}
                                <span>{account.transaction_count} txns · {accountStatements.length} stmt{accountStatements.length !== 1 ? "s" : ""}</span>
                              </div>
                            </div>
                            {accountStatements.length > 0 && (
                              <div className="border-t border-border px-3 py-2 space-y-1">
                                {accountStatements.map((stmt) => (
                                  <div
                                    key={stmt.id}
                                    onClick={(e) => e.stopPropagation()}
                                    className="flex items-center justify-between py-1 text-xs"
                                  >
                                    <div className="flex items-center gap-2 min-w-0 flex-1">
                                      <FileText className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
                                      <span className="text-foreground truncate" title={stmt.source_file_name}>
                                        {stmt.source_file_name}
                                      </span>
                                      <span className="text-muted-foreground flex-shrink-0">
                                        · {stmt.period_start} → {stmt.period_end}
                                      </span>
                                      <span className="text-muted-foreground flex-shrink-0">
                                        · {stmt.extracted_txn_count} txns
                                      </span>
                                    </div>
                                    <div className="flex items-center gap-2 flex-shrink-0">
                                      <a
                                        href={statementPdfUrl(stmt.id)}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        onClick={(e) => e.stopPropagation()}
                                        className="text-primary hover:text-primary/80"
                                        title="Open source PDF"
                                      >
                                        PDF
                                      </a>
                                      <button
                                        onClick={() => handleDelete(stmt.id, stmt.source_file_name)}
                                        disabled={deleteMut.isPending}
                                        className="text-destructive hover:bg-destructive/10 p-1 rounded disabled:opacity-50"
                                        title="Delete this statement"
                                      >
                                        {deleteMut.isPending && deleteMut.variables === stmt.id
                                          ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                          : <Trash2 className="w-3.5 h-3.5" />}
                                      </button>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="text-sm text-muted-foreground p-3 bg-background rounded-lg">(no statements yet)</div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`border-2 border-dashed rounded-lg p-12 text-center transition-colors ${
            dragOver ? 'border-primary bg-primary/10' : 'border-border bg-card'
          }`}
        >
          <Upload className={`w-12 h-12 mx-auto mb-4 ${dragOver ? 'text-primary' : 'text-muted-foreground'}`} />
          <h3 className="text-lg font-medium text-foreground mb-2">Drag & drop PDFs here</h3>
          <p className="text-muted-foreground mb-4">
            Auto-detects bank + account holder. Supports HDFC, IDFC, ICICI, Kotak, SBI, Axis…
          </p>
          <button
            onClick={() => { setUploadPersonId(undefined); setShowUpload(true); }}
            className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90"
          >
            Choose files
          </button>
        </div>

        <div className="mt-8">
          <Link
            to={`/cases/${caseId}/workbench`}
            className="inline-flex items-center gap-2 text-primary hover:text-primary/80 font-medium"
          >
            Open case workbench →
          </Link>
        </div>
      </main>

      {showUpload && (
        <UploadModal
          onClose={() => setShowUpload(false)}
          caseId={caseId!}
          personId={uploadPersonId}
          persons={persons}
        />
      )}
    </div>
  );
}
