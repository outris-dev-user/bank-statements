/**
 * Shared taxonomy constants used by both inline editors and the full drawer.
 * Keep in sync with [backend/app/entity_inference.py](../../../backend/app/entity_inference.py).
 */

export const CATEGORIES = [
  "Food",
  "Transfer",
  "Salary",
  "Rent",
  "Shopping",
  "Finance",
  "Cash",
  "Rewards",
  "Charges",
  "Other",
] as const;
export type Category = (typeof CATEGORIES)[number];

export const CHANNELS = [
  "UPI",
  "NEFT",
  "IMPS",
  "RTGS",
  "ATM",
  "POS",
  "Cheque",
  "Cash",
  "Other",
] as const;
export type Channel = (typeof CHANNELS)[number];
