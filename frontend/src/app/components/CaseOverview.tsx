import { Link, useParams, useNavigate } from "react-router";
import { mockCases, mockPersons, mockAccounts } from "../data";
import { ChevronLeft, User, Upload, Plus, CheckCircle, AlertTriangle } from "lucide-react";
import { useState } from "react";
import { UploadModal } from "./UploadModal";

export function CaseOverview() {
  const { caseId } = useParams();
  const navigate = useNavigate();
  const [showUpload, setShowUpload] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const caseItem = mockCases.find((c) => c.id === caseId);
  const persons = mockPersons.filter((p) => p.case_id === caseId);

  if (!caseItem) {
    return <div>Case not found</div>;
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = () => {
    setDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    setShowUpload(true);
  };

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
              const personAccounts = mockAccounts.filter((a) => a.person_id === person.id);
              return (
                <div key={person.id} className="bg-card rounded-lg border border-border p-6">
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <User className="w-5 h-5 text-muted-foreground" />
                      <h4 className="font-semibold text-foreground">{person.name}</h4>
                    </div>
                    <button
                      onClick={() => setShowUpload(true)}
                      className="px-4 py-2 border border-border rounded-lg hover:bg-background flex items-center gap-2 text-sm"
                    >
                      <Upload className="w-4 h-4" />
                      Upload statement
                    </button>
                  </div>

                  {personAccounts.length > 0 ? (
                    <div className="space-y-2">
                      {personAccounts.map((account) => (
                        <div
                          key={account.id}
                          onClick={() => navigate(`/cases/${caseId}/workbench?account=${account.id}`)}
                          className="flex items-center justify-between p-3 bg-background rounded-lg cursor-pointer hover:bg-muted transition-colors"
                        >
                          <div className="flex items-center gap-3">
                            <span className="text-xl">🏦</span>
                            <div>
                              <div className="font-medium text-foreground">
                                {account.bank} A/C {account.account_number} ({account.account_type})
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-2 text-sm text-muted-foreground">
                            {account.has_warnings ? (
                              <AlertTriangle className="w-4 h-4 text-amber-500" />
                            ) : (
                              <CheckCircle className="w-4 h-4 text-green-500" />
                            )}
                            <span>
                              {account.transaction_count} txns · 1 statement
                            </span>
                          </div>
                        </div>
                      ))}
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
            onClick={() => setShowUpload(true)}
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

      {showUpload && <UploadModal onClose={() => setShowUpload(false)} caseId={caseId!} />}
    </div>
  );
}
