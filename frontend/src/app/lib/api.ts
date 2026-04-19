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

const RAW_API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

/** Normalise whatever came in via VITE_API_URL: strip trailing slash, and
 *  complain loudly if the scheme prefix is missing so the next misconfig
 *  surfaces at boot instead of as a mysterious JSON parse error 20 requests
 *  later. A bare hostname like `backend.up.railway.app` is almost always
 *  a paste error — fetch() treats it as a relative path. */
function normaliseBase(raw: string): string {
  const trimmed = raw.trim().replace(/\/+$/, "");
  if (trimmed && !/^https?:\/\//i.test(trimmed)) {
    // Surface a clear diagnostic at module load. We don't auto-prepend https://
    // because "which scheme?" is a deploy-time decision, not a library guess.
    // eslint-disable-next-line no-console
    console.error(
      `[api] VITE_API_URL is missing a scheme — got "${trimmed}". ` +
      `fetch() will treat this as a relative path and requests will hit the frontend's own origin. ` +
      `Set VITE_API_URL to e.g. "https://your-backend.up.railway.app".`,
    );
  }
  return trimmed;
}

export const API_BASE = normaliseBase(RAW_API_URL);

const API_KEY = (import.meta.env.VITE_API_KEY as string | undefined) ?? "";

/** Header map to attach to every fetch against the backend. Keeps the
 *  key in one place so UploadModal (multipart) and request() (JSON) agree. */
export function apiAuthHeaders(): Record<string, string> {
  return API_KEY ? { "X-API-Key": API_KEY } : {};
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "content-type": "application/json",
        ...apiAuthHeaders(),
        ...(init?.headers ?? {}),
      },
    });
  } catch (networkErr) {
    throw new Error(
      `Network error calling ${API_BASE}${path} — ${networkErr instanceof Error ? networkErr.message : String(networkErr)}. ` +
      `Check VITE_API_URL (baked value: "${API_BASE}") and the backend's ALLOWED_ORIGINS.`,
    );
  }
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText} — ${body.slice(0, 200)}`);
  }
  // Detect "response is HTML where JSON was expected" — the classic symptom
  // of VITE_API_URL being wrong (request hit the frontend's SPA fallback).
  const text = await res.text();
  if (text.trimStart().startsWith("<")) {
    throw new Error(
      `API returned HTML instead of JSON — the request probably hit the frontend's own origin. ` +
      `VITE_API_URL was baked as "${API_BASE}". Requested path: "${path}". ` +
      `Set VITE_API_URL to the backend's public URL with the scheme prefix and rebuild.`,
    );
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new Error(`API returned invalid JSON for ${path}: ${text.slice(0, 200)}`);
  }
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

export interface CaseCreate {
  fir_number: string;
  title: string;
  officer_name: string;
}

export const createCase = (body: CaseCreate) =>
  request<Case>("/api/cases", {
    method: "POST",
    body: JSON.stringify(body),
  });

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
  `${API_BASE}/api/statements/${encodeURIComponent(statementId)}/pdf`;

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
