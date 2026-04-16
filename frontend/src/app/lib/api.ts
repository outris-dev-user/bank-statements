/**
 * HTTP client for the LedgerFlow backend.
 *
 * Shape: each fetcher returns a `Promise<T>`. Use with react-query or any
 * async state lib when we wire it in. For the static realData path today,
 * this file is unused.
 *
 * Base URL is `import.meta.env.VITE_API_URL` (defaults to http://localhost:8000).
 */
import type { Case, Person, Account, Statement, Transaction } from "../data/mockData";

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText} — ${body.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

// ───────────────── endpoints ─────────────────

export interface Health {
  status: string;
  cases: number;
  persons: number;
  accounts: number;
  statements: number;
  transactions: number;
}

export const fetchHealth = () => request<Health>("/api/health");

export const fetchCases = () => request<Case[]>("/api/cases");

export interface CaseDetail {
  case: Case;
  persons: Person[];
  accounts: Account[];
}

export const fetchCase = (caseId: string) =>
  request<CaseDetail>(`/api/cases/${encodeURIComponent(caseId)}`);

export interface TransactionPage {
  total: number;
  offset: number;
  limit: number;
  items: Transaction[];
}

export const fetchCaseTransactions = (
  caseId: string,
  params: { account_id?: string; offset?: number; limit?: number } = {},
) => {
  const q = new URLSearchParams();
  if (params.account_id) q.set("account_id", params.account_id);
  if (params.offset != null) q.set("offset", String(params.offset));
  if (params.limit != null) q.set("limit", String(params.limit));
  const qs = q.toString();
  return request<TransactionPage>(
    `/api/cases/${encodeURIComponent(caseId)}/transactions${qs ? `?${qs}` : ""}`,
  );
};

export const fetchStatement = (id: string) =>
  request<Statement>(`/api/statements/${encodeURIComponent(id)}`);

export interface TransactionPatch {
  entities?: Transaction["entities"];
  tags?: string[];
  amount?: number;
  txn_date?: string;
  review_status?: Transaction["review_status"];
}

export const patchTransaction = (id: string, patch: TransactionPatch) =>
  request<Transaction>(`/api/transactions/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });

export interface AuditEvent {
  field: string;
  old: string;
  new: string;
  at: string;
  by: string;
}

export const fetchTransactionAudit = (id: string) =>
  request<AuditEvent[]>(`/api/transactions/${encodeURIComponent(id)}/audit`);
