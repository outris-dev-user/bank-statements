/**
 * Demo-gate — a hardcoded password overlay for the Railway demo build.
 *
 * Activated when `VITE_DEMO_PASSWORD` is set at build time. On success stores
 * a flag in localStorage so a refresh doesn't re-prompt. This is *not* real
 * authentication — it's a tiny speed-bump to keep the public Railway URL
 * from being browsable by anyone who stumbles onto it during client demos.
 */
import { useState, type FormEvent, type ReactNode } from "react";
import { Lock } from "lucide-react";

const EXPECTED = (import.meta.env.VITE_DEMO_PASSWORD as string | undefined) ?? "";
const LS_KEY = "ledgerflow_demo_auth_v1";

export function DemoGate({ children }: { children: ReactNode }) {
  // No password configured → gate disabled (local dev, or production where
  // access is controlled elsewhere).
  const [authed, setAuthed] = useState(() => {
    if (!EXPECTED) return true;
    try {
      return localStorage.getItem(LS_KEY) === EXPECTED;
    } catch {
      return false;
    }
  });
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (authed) return <>{children}</>;

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (input === EXPECTED) {
      try {
        localStorage.setItem(LS_KEY, EXPECTED);
      } catch {
        // Ignore — user will just re-enter on refresh.
      }
      setAuthed(true);
      setError(null);
    } else {
      setError("Incorrect password.");
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm bg-card border border-border rounded-xl p-6 shadow-sm space-y-4"
      >
        <div className="flex items-center gap-2 text-foreground">
          <Lock className="w-5 h-5" />
          <h1 className="text-lg font-semibold" style={{ fontFamily: "var(--font-headline)" }}>
            LedgerFlow demo
          </h1>
        </div>
        <p className="text-sm text-muted-foreground">
          Enter the demo password to continue.
        </p>
        <input
          type="password"
          autoFocus
          value={input}
          onChange={(e) => { setInput(e.target.value); setError(null); }}
          placeholder="Password"
          className="w-full px-3 py-2 border border-border rounded bg-input-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
        />
        {error && (
          <div className="text-sm text-destructive">{error}</div>
        )}
        <button
          type="submit"
          disabled={!input}
          className="w-full px-3 py-2 rounded bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Continue
        </button>
      </form>
    </div>
  );
}
