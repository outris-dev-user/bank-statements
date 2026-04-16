import { X, Check, Loader2 } from "lucide-react";
import { useState, useEffect } from "react";
import { useNavigate } from "react-router";

interface UploadModalProps {
  onClose: () => void;
  caseId: string;
}

export function UploadModal({ onClose, caseId }: UploadModalProps) {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);

  const steps = [
    { label: 'Detected bank: Kotak Mahindra', done: false },
    { label: 'Extracted text (pdfplumber, 240ms)', done: false },
    { label: 'Parsed 240 transactions', done: false },
    { label: 'Sum-check: 100% (matches declared totals)', done: false },
    { label: 'Resolving entities...', done: false },
    { label: 'Reconciling across case', done: false },
  ];

  useEffect(() => {
    if (step < steps.length) {
      const timer = setTimeout(() => {
        setStep(step + 1);
      }, 800);
      return () => clearTimeout(timer);
    }
  }, [step]);

  const handleOpenWorkbench = () => {
    navigate(`/cases/${caseId}/workbench`);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-card rounded-lg shadow-xl w-full max-w-2xl mx-4">
        <div className="border-b border-border px-6 py-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">Uploading: Statement April-Aug 2021.pdf</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-muted-foreground">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6">
          <div className="text-sm text-muted-foreground mb-6">Size: 256 KB · 10 pages</div>

          <div className="space-y-3 mb-8">
            {steps.map((stepItem, idx) => (
              <div key={idx} className="flex items-center gap-3">
                {idx < step ? (
                  <Check className="w-5 h-5 text-[color:var(--fl-emerald-500)] flex-shrink-0" />
                ) : idx === step ? (
                  <Loader2 className="w-5 h-5 text-primary animate-spin flex-shrink-0" />
                ) : (
                  <div className="w-5 h-5 rounded-full border-2 border-border flex-shrink-0" />
                )}
                <span className={idx <= step ? 'text-foreground' : 'text-muted-foreground'}>{stepItem.label}</span>
              </div>
            ))}
          </div>

          {step >= steps.length && (
            <div className="space-y-4">
              <div className="bg-background rounded-lg p-4 space-y-3">
                <div className="text-sm">
                  <span className="text-muted-foreground">Account holder detected:</span>{' '}
                  <span className="font-medium text-foreground">Suraj Shyam More</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-muted-foreground">Link to person:</span>
                  <select className="flex-1 px-3 py-2 border border-border rounded-lg text-sm">
                    <option>Suraj Shyam More</option>
                    <option>+ New person</option>
                  </select>
                </div>
                <div className="text-sm">
                  <span className="text-muted-foreground">Account:</span>{' '}
                  <span className="font-medium text-foreground">Kotak A/C 7894231652</span>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="border-t border-border px-6 py-4 flex items-center justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 border border-border rounded-lg hover:bg-background">
            Cancel
          </button>
          {step >= steps.length && (
            <button
              onClick={handleOpenWorkbench}
              className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90"
            >
              Open workbench
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
