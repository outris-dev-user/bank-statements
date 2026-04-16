/**
 * Data-source facade.
 *
 * Components import the neutral names (`mockCases`, `mockPersons`, …)
 * from `../data`; what they actually get is the real extracted data
 * from `tools/export-for-frontend.py`.
 *
 * To fall back to the hand-authored mock data (only a handful of
 * illustrative rows, useful for UX stress-tests), swap the import line
 * below:
 *
 *     // current — real data (858 transactions from the benchmark):
 *     export { realCases as mockCases, ... } from './realData';
 *
 *     // to fall back to the tiny mock set:
 *     // export { mockCases, ... } from './mockData';
 *
 * Types always come from `./mockData` — that file is the schema SoT
 * and `realData.ts` imports its types from there.
 */

export type {
  Case,
  Person,
  Account,
  Statement,
  Transaction,
  EntityValue,
} from './mockData';

export {
  realCases as mockCases,
  realPersons as mockPersons,
  realAccounts as mockAccounts,
  realStatements as mockStatements,
  realTransactions as mockTransactions,
} from './realData';
