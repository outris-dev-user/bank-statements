// Mock data for bank statement analysis tool

export interface Case {
  id: string;
  fir_number: string;
  title: string;
  officer_name: string;
  status: 'active' | 'archived' | 'closed';
  created_at: string;
  updated_at: string;
  statement_count: number;
  transaction_count: number;
  flag_count: number;
}

export interface Person {
  id: string;
  case_id: string;
  name: string;
  aliases: string[];
  pan?: string;
  phone?: string;
  notes?: string;
}

export interface Account {
  id: string;
  person_id: string;
  bank: string;
  account_type: 'SA' | 'CA' | 'CC' | 'OD';
  account_number: string;
  holder_name: string;
  currency: string;
  transaction_count: number;
  has_warnings: boolean;
}

export interface Statement {
  id: string;
  account_id: string;
  source_file_name: string;
  period_start: string;
  period_end: string;
  opening_balance: number;
  closing_balance: number;
  extracted_txn_count: number;
  sum_check_debits_pct: number;
  sum_check_credits_pct: number;
  uploaded_at: string;
  uploaded_by: string;
}

export interface EntityValue {
  value: string;
  source: 'extracted' | 'user_edited' | 'auto_resolved';
  confidence: number;
}

export interface Transaction {
  id: string;
  statement_id: string;
  account_id: string;
  case_id: string;
  row_index: number;
  txn_date: string;
  amount: number;
  direction: 'Dr' | 'Cr';
  running_balance: number;
  raw_description: string;
  entities: {
    channel?: EntityValue;
    counterparty?: EntityValue;
    category?: EntityValue;
    ref_number?: EntityValue;
  };
  tags: string[];
  confidence: 'high' | 'medium' | 'low';
  flags: string[];
  review_status: 'unreviewed' | 'reviewed' | 'flagged';
  edit_count: number;
}

export const mockCases: Case[] = [
  {
    id: '1',
    fir_number: 'FIR # 2026/AEC/0471',
    title: 'Suraj Shyam More — Kotak + HDFC Sav',
    officer_name: 'SI A. Kamat',
    status: 'active',
    created_at: '2026-04-13T10:30:00',
    updated_at: '2026-04-15T12:15:00',
    statement_count: 2,
    transaction_count: 792,
    flag_count: 3,
  },
  {
    id: '2',
    fir_number: 'FIR # 2026/AEC/0466',
    title: 'Bilal A. K. Mohammed — HDFC Savings (Oct 23 - Mar 24)',
    officer_name: 'Inspector R. Desai',
    status: 'active',
    created_at: '2026-04-14T09:00:00',
    updated_at: '2026-04-14T16:45:00',
    statement_count: 1,
    transaction_count: 554,
    flag_count: 12,
  },
  {
    id: '3',
    fir_number: 'FIR # 2025/MPN/1201',
    title: 'Atul Kabra — ICICI Current',
    officer_name: 'SI M. Sharma',
    status: 'archived',
    created_at: '2025-12-10T08:00:00',
    updated_at: '2026-04-01T10:00:00',
    statement_count: 1,
    transaction_count: 37,
    flag_count: 0,
  },
];

export const mockPersons: Person[] = [
  {
    id: 'p1',
    case_id: '1',
    name: 'Suraj Shyam More',
    aliases: [],
    pan: 'ABCDE1234F',
    phone: '+91 98765 43210',
  },
  {
    id: 'p2',
    case_id: '1',
    name: 'Meera Patel',
    aliases: [],
  },
];

export const mockAccounts: Account[] = [
  {
    id: 'a1',
    person_id: 'p1',
    bank: 'Kotak Mahindra',
    account_type: 'CA',
    account_number: '7894231652',
    holder_name: 'Suraj Shyam More',
    currency: 'INR',
    transaction_count: 240,
    has_warnings: false,
  },
  {
    id: 'a2',
    person_id: 'p1',
    bank: 'HDFC Bank',
    account_type: 'SA',
    account_number: '****8420',
    holder_name: 'Suraj Shyam More',
    currency: 'INR',
    transaction_count: 554,
    has_warnings: true,
  },
];

export const mockStatements: Statement[] = [
  {
    id: 's1',
    account_id: 'a1',
    source_file_name: 'Kotak_Apr2021.pdf',
    period_start: '2021-04-01',
    period_end: '2021-04-30',
    opening_balance: 15829,
    closing_balance: 3329,
    extracted_txn_count: 87,
    sum_check_debits_pct: 100,
    sum_check_credits_pct: 100,
    uploaded_at: '2026-04-15T12:04:00',
    uploaded_by: 'Saurabh',
  },
  {
    id: 's2',
    account_id: 'a1',
    source_file_name: 'Kotak_May2021.pdf',
    period_start: '2021-05-01',
    period_end: '2021-05-31',
    opening_balance: 16012,
    closing_balance: 8234,
    extracted_txn_count: 153,
    sum_check_debits_pct: 100,
    sum_check_credits_pct: 100,
    uploaded_at: '2026-04-15T12:05:00',
    uploaded_by: 'Saurabh',
  },
  {
    id: 's3',
    account_id: 'a2',
    source_file_name: 'HDFC_Oct23_Mar24.pdf',
    period_start: '2023-10-01',
    period_end: '2024-03-31',
    opening_balance: 125000,
    closing_balance: 167893,
    extracted_txn_count: 554,
    sum_check_debits_pct: 99.8,
    sum_check_credits_pct: 100,
    uploaded_at: '2026-04-15T12:10:00',
    uploaded_by: 'Saurabh',
  },
];

export const mockTransactions: Transaction[] = [
  {
    id: 't1',
    statement_id: 's1',
    account_id: 'a1',
    case_id: '1',
    row_index: 1,
    txn_date: '2021-04-01',
    amount: 200,
    direction: 'Dr',
    running_balance: 3129,
    raw_description: 'UPI/Trilok Saxena/9876543210',
    entities: {
      channel: { value: 'UPI', source: 'extracted', confidence: 1.0 },
      counterparty: { value: 'Trilok Saxena', source: 'extracted', confidence: 0.95 },
      category: { value: 'Transfer', source: 'auto_resolved', confidence: 0.8 },
    },
    tags: [],
    confidence: 'high',
    flags: [],
    review_status: 'unreviewed',
    edit_count: 0,
  },
  {
    id: 't2',
    statement_id: 's1',
    account_id: 'a1',
    case_id: '1',
    row_index: 2,
    txn_date: '2021-04-01',
    amount: 12683,
    direction: 'Dr',
    running_balance: 3329,
    raw_description: 'UPI/CRED/109108427041/credit card bil',
    entities: {
      channel: { value: 'UPI', source: 'extracted', confidence: 1.0 },
      counterparty: { value: 'CRED', source: 'extracted', confidence: 0.85 },
      category: { value: 'Finance', source: 'auto_resolved', confidence: 0.7 },
      ref_number: { value: '109108427041', source: 'extracted', confidence: 1.0 },
    },
    tags: ['credit-card'],
    confidence: 'medium',
    flags: ['SUM_CHECK_CONTRIBUTOR'],
    review_status: 'flagged',
    edit_count: 0,
  },
  {
    id: 't3',
    statement_id: 's1',
    account_id: 'a1',
    case_id: '1',
    row_index: 3,
    txn_date: '2021-04-01',
    amount: 10000,
    direction: 'Cr',
    running_balance: 16012,
    raw_description: 'UPI/Sarika Lalasaheb/9988776655',
    entities: {
      channel: { value: 'UPI', source: 'extracted', confidence: 1.0 },
      counterparty: { value: 'Sarika Lalasaheb', source: 'extracted', confidence: 0.9 },
      category: { value: 'Transfer', source: 'auto_resolved', confidence: 0.75 },
    },
    tags: [],
    confidence: 'high',
    flags: [],
    review_status: 'unreviewed',
    edit_count: 0,
  },
  {
    id: 't4',
    statement_id: 's2',
    account_id: 'a1',
    case_id: '1',
    row_index: 1,
    txn_date: '2021-05-02',
    amount: 510,
    direction: 'Dr',
    running_balance: 15502,
    raw_description: 'UPI/Amazon/Ord#45623441',
    entities: {
      channel: { value: 'UPI', source: 'extracted', confidence: 1.0 },
      counterparty: { value: 'Amazon', source: 'extracted', confidence: 0.98 },
      category: { value: 'Shopping', source: 'auto_resolved', confidence: 0.85 },
      ref_number: { value: 'Ord#45623441', source: 'extracted', confidence: 0.9 },
    },
    tags: [],
    confidence: 'high',
    flags: [],
    review_status: 'unreviewed',
    edit_count: 0,
  },
  {
    id: 't5',
    statement_id: 's2',
    account_id: 'a1',
    case_id: '1',
    row_index: 2,
    txn_date: '2021-05-05',
    amount: 1350,
    direction: 'Dr',
    running_balance: 14152,
    raw_description: 'ATM/CHETAN WINES/MUMBAI',
    entities: {
      channel: { value: 'ATM', source: 'extracted', confidence: 1.0 },
      counterparty: { value: 'CHETAN WINES', source: 'extracted', confidence: 0.75 },
      category: { value: 'Cash', source: 'auto_resolved', confidence: 0.6 },
    },
    tags: [],
    confidence: 'medium',
    flags: ['NEEDS_REVIEW'],
    review_status: 'unreviewed',
    edit_count: 0,
  },
  {
    id: 't6',
    statement_id: 's2',
    account_id: 'a1',
    case_id: '1',
    row_index: 3,
    txn_date: '2021-05-20',
    amount: 1000,
    direction: 'Dr',
    running_balance: 13152,
    raw_description: 'IMPS/351123456789/PAYMENT',
    entities: {
      channel: { value: 'IMPS', source: 'extracted', confidence: 1.0 },
      counterparty: { value: '(unknown: 3511...)', source: 'extracted', confidence: 0.3 },
      category: { value: 'Transfer', source: 'auto_resolved', confidence: 0.5 },
      ref_number: { value: '351123456789', source: 'extracted', confidence: 0.95 },
    },
    tags: [],
    confidence: 'low',
    flags: ['NEEDS_REVIEW'],
    review_status: 'unreviewed',
    edit_count: 0,
  },
  {
    id: 't7',
    statement_id: 's2',
    account_id: 'a1',
    case_id: '1',
    row_index: 4,
    txn_date: '2021-05-22',
    amount: 2,
    direction: 'Cr',
    running_balance: 13154,
    raw_description: 'UPI/Google Pay/Cashback',
    entities: {
      channel: { value: 'UPI', source: 'extracted', confidence: 1.0 },
      counterparty: { value: 'Google Pay', source: 'extracted', confidence: 0.95 },
      category: { value: 'Rewards', source: 'auto_resolved', confidence: 0.9 },
    },
    tags: [],
    confidence: 'high',
    flags: [],
    review_status: 'unreviewed',
    edit_count: 0,
  },
];
