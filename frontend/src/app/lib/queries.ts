/**
 * react-query hooks over the typed fetchers in `./api`.
 *
 * Components consume these instead of importing static `mock*` data.
 * Query keys are kept flat and prefixed so devtools grouping is obvious.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchCase,
  fetchCases,
  fetchCaseSummary,
  fetchCaseTransactions,
  fetchHealth,
  fetchTransactionAudit,
  patchTransaction,
  runPatterns,
  type TransactionPatch,
} from "./api";

export const qk = {
  health: () => ["health"] as const,
  cases: () => ["cases"] as const,
  case: (id: string) => ["case", id] as const,
  caseSummary: (id: string) => ["case", id, "summary"] as const,
  caseTxns: (id: string, accountId?: string) =>
    ["case", id, "transactions", accountId ?? "all"] as const,
  txnAudit: (id: string) => ["transaction", id, "audit"] as const,
};

export const useHealth = () => useQuery({ queryKey: qk.health(), queryFn: fetchHealth });

export const useCases = () => useQuery({ queryKey: qk.cases(), queryFn: fetchCases });

export const useCase = (caseId: string | undefined) =>
  useQuery({
    queryKey: qk.case(caseId ?? ""),
    queryFn: () => fetchCase(caseId!),
    enabled: !!caseId,
  });

export const useCaseTransactions = (
  caseId: string | undefined,
  accountId?: string,
  limit = 2000,
) =>
  useQuery({
    queryKey: qk.caseTxns(caseId ?? "", accountId),
    queryFn: () =>
      fetchCaseTransactions(caseId!, { account_id: accountId, limit }),
    enabled: !!caseId,
  });

export const useCaseSummary = (caseId: string | undefined) =>
  useQuery({
    queryKey: qk.caseSummary(caseId ?? ""),
    queryFn: () => fetchCaseSummary(caseId!),
    enabled: !!caseId,
  });

export const useRunPatterns = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (caseId: string) => runPatterns(caseId),
    onSuccess: (_data, caseId) => {
      qc.invalidateQueries({ queryKey: ["case", caseId] });
      qc.invalidateQueries({ queryKey: qk.caseSummary(caseId) });
    },
  });
};

export const useTransactionAudit = (txnId: string | undefined) =>
  useQuery({
    queryKey: qk.txnAudit(txnId ?? ""),
    queryFn: () => fetchTransactionAudit(txnId!),
    enabled: !!txnId,
  });

export const usePatchTransaction = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: TransactionPatch }) =>
      patchTransaction(id, patch),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["case"] });
      qc.invalidateQueries({ queryKey: qk.txnAudit(vars.id) });
    },
  });
};
