/**
 * HTTP client for the LedgerFlow backend.
 *
 * Shape: each fetcher returns a `Promise<T>`. Use with react-query or any
 * async state lib when we wire it in. For the static realData path today,
 * this file is unused.
 *
 * Base URL is `import.meta.env.VITE_API_URL` (defaults to http://localhost:8000).
 * When `VITE_API_KEY` is set (Railway prod build), every request attaches an
 * `X-API-Key` header so the backend's key gate accepts the call.
 */
import type { Case, Person, Account, Statement, Transaction } from "../data/mockData";

export const API_BASE =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

const API_KEY = (import.meta.env.VITE_API_KEY as string | undefined) ?? "";

/** Header map to attach to every fetch against the backend. Keeps the
 *  key in one place so UploadModal (multipart) and request() (JSON) agree. */
export function apiAuthHeaders(): Record<string, string> {
  return API_KEY ? { "X-API-Key": API_KEY } : {};
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...apiAuthHeaders(),
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
  statements: Statement[];
}

export const fetchCase = (caseId: string) =>
  request<CaseDetail>(`/api/cases/${encodeURIComponent(caseId)}`);

export interface PersonCreate {
  name: string;
  pan?: string;
  phone?: string;
}

export const createPerson = (caseId: string, body: PersonCreate) =>
  request<Person>(`/api/cases/${encodeURIComponent(caseId)}/persons`, {
    method: "POST",
    body: JSON.stringify(body),
  });

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

export const statementPdfUrl = (statementId: string): string =>
  `${BASE}/api/statements/${encodeURIComponent(statementId)}/pdf`;

export const deleteStatement = (statementId: string) =>
  request<{ status: string; transactions_deleted: number; account_deleted: boolean }>(
    `/api/statements/${encodeURIComponent(statementId)}`,
    { method: "DELETE" },
  );

export interface GraphNode {
  id: string;
  label: string;
  type: "person" | "account" | "entity";
  size: number;
  meta: Record<string, any>;
}

export interface GraphEdgeSample {
  id: string;
  txn_date: string;
  amount: number;
  direction: "Dr" | "Cr";
  raw_description: string;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  kind: "owns" | "flow_in" | "flow_out";
  total_amount: number;
  txn_count: number;
  date_min?: string;
  date_max?: string;
  sample_txn_ids: string[];
  sample_txns: GraphEdgeSample[];
}

export interface MonthlyActivityPoint {
  month: string; // "YYYY-MM"
  count: number;
}

export interface CaseGraph {
  case_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  monthly_activity?: MonthlyActivityPoint[];
}

export const fetchCaseGraph = (caseId: string) =>
  request<CaseGraph>(`/api/cases/${encodeURIComponent(caseId)}/graph`);

export interface MonthlyPoint {
  month: string;
  dr_total: number;
  cr_total: number;
  count: number;
}

export interface TopCounterparty {
  name: string;
  count: number;
  total_dr: number;
  total_cr: number;
}

export interface CategoryBreakdown {
  category: string;
  count: number;
  total_dr: number;
  total_cr: number;
}

export interface PatternHit {
  name: string;
  label: string;
  description: string;
  severity: "low" | "medium" | "high";
  count: number;
  sample_txn_ids: string[];
}

export interface CaseSummary {
  total_dr: number;
  total_cr: number;
  net: number;
  txn_count: number;
  flag_count: number;
  reviewed_count: number;
  unreviewed_count: number;
  flagged_count: number;
  monthly: MonthlyPoint[];
  top_counterparties: TopCounterparty[];
  categories: CategoryBreakdown[];
  patterns: PatternHit[];
}

export const fetchCaseSummary = (caseId: string) =>
  request<CaseSummary>(`/api/cases/${encodeURIComponent(caseId)}/summary`);

export const runPatterns = (caseId: string) =>
  request<{ status: string; flags_added: Record<string, number> }>(
    `/api/cases/${encodeURIComponent(caseId)}/run-patterns`,
    { method: "POST" },
  );

export interface Entity {
  id: string;
  case_id: string;
  name: string;
  canonical_key: string;
  entity_type: string;
  pan?: string;
  phone?: string;
  notes?: string;
  linked_person_id?: string;
  aliases: string[];
  created_at: string;
  auto_created: boolean;
  txn_count: number;
  total_dr: number;
  total_cr: number;
}

export interface EntityDetailPayload {
  entity: Entity;
  transactions: Transaction[];
}

export const fetchEntities = (caseId: string) =>
  request<Entity[]>(`/api/cases/${encodeURIComponent(caseId)}/entities`);

export const fetchEntity = (entityId: string) =>
  request<EntityDetailPayload>(`/api/entities/${encodeURIComponent(entityId)}`);

export const resolveEntities = (caseId: string) =>
  request<{ status: string; entities_created: number; entities_updated: number; groups: number }>(
    `/api/cases/${encodeURIComponent(caseId)}/resolve-entities`,
    { method: "POST" },
  );

export const linkTransactionEntity = (txnId: string, entityId: string, role = "counterparty") =>
  request<{ status: string }>(`/api/transactions/${encodeURIComponent(txnId)}/entity-links`, {
    method: "POST",
    body: JSON.stringify({ entity_id: entityId, role }),
  });

export const unlinkTransactionEntity = (txnId: string, entityId: string) =>
  request<{ status: string }>(
    `/api/transactions/${encodeURIComponent(txnId)}/entity-links/${encodeURIComponent(entityId)}`,
    { method: "DELETE" },
  );

export const fetchTransactionEntities = (txnId: string) =>
  request<Entity[]>(`/api/transactions/${encodeURIComponent(txnId)}/entities`);

export interface TransactionPatch {
  entities?: Transaction["entities"];
  tags?: string[];
  amount?: number;
  direction?: Transaction["direction"];
  txn_date?: string;
  review_status?: Transaction["review_status"];
}

export type { Person } from "../data/mockData";

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
