import { createClient } from '@/lib/supabase'

// Empty in production: calls go to /api/* on the same origin and Next proxies them.
// Set NEXT_PUBLIC_API_URL=http://localhost:8000 in .env.local to hit the API directly in dev.
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ''

async function getToken(): Promise<string> {
  const { data: { session } } = await createClient().auth.getSession()
  if (!session) throw new Error('Not authenticated')
  return session.access_token
}

// FastAPI returns `detail` as a string for HTTPException but as a list of {loc,msg} for 422s.
async function errorMessage(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => ({})) as { detail?: unknown }
  const d = body.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) {
    return d
      .map((e: { loc?: unknown[]; msg?: string }) => `${(e.loc ?? []).slice(1).join('.') || 'field'}: ${e.msg ?? 'invalid'}`)
      .join('; ')
  }
  return fallback
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await getToken()
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  })
  if (!res.ok) {
    throw new Error(await errorMessage(res, `Request failed (${res.status})`))
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

// ── Document Upload ────────────────────────────────────────────────────────────

export type DocType = 'auto' | 'payslip' | 'bank_statement' | 'form16' | 'cas_statement'

export interface UploadResult {
  success: boolean
  doc_type: string
  data: Record<string, unknown>
  confidence?: string
  raw_extraction?: string
}

export function uploadDocument(
  file: File,
  docType: DocType,
  onProgress?: (pct: number) => void,
  password?: string,
): Promise<UploadResult> {
  return new Promise(async (resolve, reject) => {
    let token: string
    try {
      token = await getToken()
    } catch (err) {
      reject(err)
      return
    }

    const form = new FormData()
    form.append('file', file)
    form.append('doc_type', docType)
    if (password) form.append('password', password)

    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE}/api/v1/documents/upload`)
    xhr.setRequestHeader('Authorization', `Bearer ${token}`)

    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100))
      }
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as UploadResult)
        } catch {
          reject(new Error('Invalid response from server'))
        }
      } else {
        let msg = `Upload failed (${xhr.status})`
        try {
          const body = JSON.parse(xhr.responseText) as { detail?: string }
          if (body.detail) msg = body.detail
        } catch {}
        reject(new Error(msg))
      }
    }

    xhr.onerror = () => reject(new Error('Network error'))
    xhr.send(form)
  })
}

// ── Save Payslip ───────────────────────────────────────────────────────────────

const MONTH_NAMES: Record<string, number> = {
  january: 1, jan: 1, february: 2, feb: 2, march: 3, mar: 3,
  april: 4, apr: 4, may: 5, june: 6, jun: 6, july: 7, jul: 7,
  august: 8, aug: 8, september: 9, sep: 9, october: 10, oct: 10,
  november: 11, nov: 11, december: 12, dec: 12,
}

function parseMonthYear(s: string | null | undefined): { month: number; year: number } | null {
  if (!s) return null
  const parts = s.trim().toLowerCase().split(/[\s,/\-]+/)
  let month = 0, year = 0
  for (const p of parts) {
    if (MONTH_NAMES[p]) {
      month = MONTH_NAMES[p]
    } else if (/^\d{4}$/.test(p)) {
      year = parseInt(p, 10)
    } else if (/^\d{1,2}$/.test(p) && !month) {
      const m = parseInt(p, 10)
      if (m >= 1 && m <= 12) month = m
    }
  }
  return month >= 1 && year >= 2000 ? { month, year } : null
}

export interface SavedSalaryRecord {
  id: string
  month: number
  year: number
  employer_name?: string
  gross_pay?: number
  net_pay?: number
}

export async function savePayslip(data: Record<string, unknown>): Promise<SavedSalaryRecord> {
  const parsed = parseMonthYear(data.month as string | undefined)
  if (!parsed) {
    throw new Error(
      'Could not parse month/year from extracted data. ' +
      'Check that the "month" field (e.g. "March 2024") was extracted correctly.'
    )
  }

  return apiFetch<SavedSalaryRecord>('/api/v1/salary/', {
    method: 'POST',
    body: JSON.stringify({
      month: parsed.month,
      year: parsed.year,
      employer_name: data.employer ?? null,
      basic: data.basic ?? null,
      hra: data.hra ?? null,
      pf_employee: data.pf_employee ?? null,
      pf_employer: data.pf_employer ?? null,
      professional_tax: data.professional_tax ?? null,
      income_tax: data.tds ?? null,
      gross_pay: data.gross_salary ?? null,
      net_pay: data.net_salary ?? null,
    }),
  })
}

// ── Manual-entry resources (holdings, loans, EPF/NPS) ──────────────────────────

export interface Holding {
  id: string
  symbol: string
  name: string
  holding_type: 'STOCK' | 'MF' | 'ETF' | 'BOND' | 'SGB' | 'OTHER'
  units: number
  current_price?: number | null
  avg_buy_price?: number | null
}

export interface Loan {
  id: string
  loan_type: 'HOME_LOAN' | 'PERSONAL_LOAN' | 'VEHICLE_LOAN' | 'CREDIT_CARD' | 'OTHER'
  lender_name?: string | null
  outstanding_amount: number
  emi_amount?: number | null
  interest_rate?: number | null
  tenure_months?: number | null
  start_date?: string | null
  principal_amount?: number | null
}

export interface EpfNps {
  id: string
  account_type: 'EPF' | 'NPS_TIER1' | 'NPS_TIER2'
  balance: number
  as_of_date: string
}

export type Resource = 'holdings' | 'loans' | 'epf-nps'

export const listItems = <T>(r: Resource) => apiFetch<T[]>(`/api/v1/${r}/`)
export const createItem = <T>(r: Resource, body: Record<string, unknown>) =>
  apiFetch<T>(`/api/v1/${r}/`, { method: 'POST', body: JSON.stringify(body) })
export const deleteItem = (r: Resource, id: string) =>
  apiFetch<void>(`/api/v1/${r}/${id}`, { method: 'DELETE' })

// ── Bank transactions ──────────────────────────────────────────────────────────

export interface Transaction {
  id: string
  transaction_date: string
  description: string
  amount: number
  category?: string | null
  bank_name?: string | null
  account_last4?: string | null
  account_id?: string | null
}

export interface MonthlySummary {
  month: string
  income: number
  expenses: number
  net: number
  by_category: { category: string; total: number }[]
}

export interface ImportResult {
  parsed: number
  inserted: number
  duplicates_skipped: number
}

const acct = (accountId?: string) => (accountId ? `&account_id=${encodeURIComponent(accountId)}` : '')

export const listTransactions = (month: string, category?: string, accountId?: string) =>
  apiFetch<Transaction[]>(
    `/api/v1/transactions/?month=${month}${category ? `&category=${encodeURIComponent(category)}` : ''}${acct(accountId)}`,
  )
export const getMonthlySummary = (month: string, accountId?: string) =>
  apiFetch<MonthlySummary>(`/api/v1/transactions/summary?month=${month}${acct(accountId)}`)
export const listCategories = () => apiFetch<string[]>('/api/v1/transactions/categories')
export const createTransaction = (body: Record<string, unknown>) =>
  apiFetch<Transaction>('/api/v1/transactions/', { method: 'POST', body: JSON.stringify(body) })
export const updateTransactionCategory = (id: string, category: string) =>
  apiFetch<Transaction>(`/api/v1/transactions/${id}`, { method: 'PATCH', body: JSON.stringify({ category }) })
export const deleteTransaction = (id: string) =>
  apiFetch<void>(`/api/v1/transactions/${id}`, { method: 'DELETE' })

export async function importStatement(
  file: File, bankName?: string, password?: string, accountId?: string,
): Promise<ImportResult> {
  const token = await getToken()
  const form = new FormData()
  form.append('file', file)
  if (bankName) form.append('bank_name', bankName)
  if (password) form.append('password', password)
  if (accountId) form.append('account_id', accountId)
  const res = await fetch(`${API_BASE}/api/v1/transactions/import`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  })
  if (!res.ok) {
    throw new Error(await errorMessage(res, `Import failed (${res.status})`))
  }
  return res.json() as Promise<ImportResult>
}

// ── Salary ─────────────────────────────────────────────────────────────────────

export interface SalaryRecord {
  id: string
  month: number
  year: number
  employer_name?: string | null
  basic?: number | null
  hra?: number | null
  pf_employee?: number | null
  income_tax?: number | null
  professional_tax?: number | null
  gross_pay?: number | null
  net_pay?: number | null
}

export const listSalary = () => apiFetch<SalaryRecord[]>('/api/v1/salary/')
export const deleteSalary = (id: string) => apiFetch<void>(`/api/v1/salary/${id}`, { method: 'DELETE' })

// The API prefixes password problems with these codes (422).
export const isPasswordError = (msg: string) => /^PASSWORD_(REQUIRED|INCORRECT)/.test(msg)
export const cleanPasswordMessage = (msg: string) => msg.replace(/^PASSWORD_[A-Z]+:\s*/, '')

// ── AI key (bring your own) ────────────────────────────────────────────────────

export interface AISettings {
  mode: 'own' | 'shared' | 'none'
  provider?: 'gemini' | 'anthropic' | null
  key_last4?: string | null
}

export const getAISettings = () => apiFetch<AISettings>('/api/v1/settings/ai')
export const saveAIKey = (provider: 'gemini' | 'anthropic', apiKey: string) =>
  apiFetch<AISettings>('/api/v1/settings/ai-key', {
    method: 'PUT',
    body: JSON.stringify({ provider, api_key: apiKey }),
  })
export const deleteAIKey = () => apiFetch<void>('/api/v1/settings/ai-key', { method: 'DELETE' })

// The API prefixes AI problems with these codes: a missing or rejected key (402) or a used-up quota (429).
// All of them are fixed from Settings (add or replace a key), so they share one handler in the UI.
export const isKeyError = (msg: string) => /^AI_(KEY_(REQUIRED|INVALID)|QUOTA)/.test(msg)
export const cleanKeyMessage = (msg: string) => msg.replace(/^AI_[A-Z_]+:\s*/, '')

// A key typed on the sign-up form is parked here until the user has a session to save it with.
const PENDING_KEY = 'porulux.pendingAIKey'
export function rememberPendingKey(provider: 'gemini' | 'anthropic', apiKey: string) {
  try { sessionStorage.setItem(PENDING_KEY, JSON.stringify({ provider, apiKey })) } catch {}
}
export async function savePendingKeyIfAny(): Promise<boolean> {
  try {
    const raw = sessionStorage.getItem(PENDING_KEY)
    if (!raw) return false
    const { provider, apiKey } = JSON.parse(raw) as { provider: 'gemini' | 'anthropic'; apiKey: string }
    await saveAIKey(provider, apiKey)
    sessionStorage.removeItem(PENDING_KEY)
    return true
  } catch {
    return false
  }
}

// ── Generic edit + salary / transaction writes ─────────────────────────────────

export const updateItem = <T>(r: Resource, id: string, body: Record<string, unknown>) =>
  apiFetch<T>(`/api/v1/${r}/${id}`, { method: 'PATCH', body: JSON.stringify(body) })

export const createSalary = (body: Record<string, unknown>) =>
  apiFetch<SalaryRecord>('/api/v1/salary/', { method: 'POST', body: JSON.stringify(body) })
export const updateSalary = (id: string, body: Record<string, unknown>) =>
  apiFetch<SalaryRecord>(`/api/v1/salary/${id}`, { method: 'PATCH', body: JSON.stringify(body) })

export const updateTransaction = (id: string, body: Record<string, unknown>) =>
  apiFetch<Transaction>(`/api/v1/transactions/${id}`, { method: 'PATCH', body: JSON.stringify(body) })

// ── Insights ───────────────────────────────────────────────────────────────────

export interface TrendMonth {
  month: string
  income: number
  expenses: number
  net: number
  categories: Record<string, number>
}
export interface SpendTrend {
  months: TrendMonth[]
  top_categories: string[]
  average_monthly_spend: number
}
export const getSpendTrend = (months = 6, accountId?: string) =>
  apiFetch<SpendTrend>(`/api/v1/transactions/trend?months=${months}${acct(accountId)}`)

export interface RecurringItem {
  name: string
  direction: 'expense' | 'income'
  frequency: 'monthly' | 'quarterly'
  typical_amount: number
  monthly_cost: number
  occurrences: number
  last_date: string
  next_expected: string
  variable: boolean
}
export const getRecurring = (accountId?: string) =>
  apiFetch<{ items: RecurringItem[]; monthly_commitments: number }>(
    `/api/v1/transactions/recurring${accountId ? `?account_id=${encodeURIComponent(accountId)}` : ''}`,
  )

export interface HoldingReturn {
  holding_id: string
  source?: string | null
  symbol: string
  name: string
  holding_type: string
  units: number
  invested: number | null
  current_value: number | null
  gain: number | null
  absolute_return_pct: number | null
  xirr_pct: number | null
  xirr_approx?: boolean
  lots: number
  price_status?: 'live' | 'cached' | 'stale' | 'manual'
  price_source?: string | null
  price_updated_at?: string | null
}
export interface InvestmentReturns {
  holdings: HoldingReturn[]
  portfolio: {
    invested: number
    current_value: number
    gain: number
    absolute_return_pct: number | null
    xirr_pct: number | null
    xirr_approx?: boolean
  }
  prices?: { updated_at: string | null; live: number; cached: number; stale: number; manual: number }
}
// refresh: 'off' = stored prices instantly, 'auto' = refresh anything older than the freshness window, 'force' = refresh all
export const getInvestmentReturns = (refresh: 'auto' | 'force' | 'off' = 'auto') =>
  apiFetch<InvestmentReturns>(`/api/v1/investments/returns?refresh=${refresh}`)

export interface Lot {
  id: string
  assumed?: boolean
  lot_date: string
  lot_type: 'BUY' | 'SELL'
  units: number
  price: number
}
export const listLots = (holdingId: string) => apiFetch<Lot[]>(`/api/v1/holdings/${holdingId}/lots`)
export const addLot = (holdingId: string, body: { lot_date: string; lot_type: 'BUY' | 'SELL'; units: number; price: number }) =>
  apiFetch<Lot>(`/api/v1/holdings/${holdingId}/lots`, { method: 'POST', body: JSON.stringify(body) })
export const deleteLot = (id: string) => apiFetch<void>(`/api/v1/lots/${id}`, { method: 'DELETE' })

export interface LoanTax {
  financial_year: string
  interest: number
  principal: number
  emis: number
  deduction_24b: number
  deduction_80c_principal: number
}
export interface LoanTracker {
  loan: Loan & { principal_amount?: number | null; tenure_months?: number | null; start_date?: string | null }
  summary: {
    original_principal: number
    emi: number
    emis_paid: number
    emis_remaining: number
    interest_paid_to_date: number
    principal_paid_to_date: number
    outstanding_principal: number
    total_interest: number
    payoff_date: string | null
    tax_by_year: LoanTax[]
    current_financial_year: string
  }
  tax_applicable: boolean
  schedule: {
    number: number
    due_date: string
    opening: number
    interest: number
    principal: number
    emi: number
    closing: number
    paid: boolean
  }[]
}
export const getLoanTracker = (id: string) => apiFetch<LoanTracker>(`/api/v1/loan-tracker/${id}`)

// ── Profile ────────────────────────────────────────────────────────────────────

export interface Profile {
  full_name?: string | null
  phone?: string | null
  address_line1?: string | null
  address_line2?: string | null
  city?: string | null
  state?: string | null
  postal_code?: string | null
  country?: string | null
  email?: string | null
  avatar_url?: string | null
}

export const getProfile = () => apiFetch<Profile>('/api/v1/profile')
export const saveProfile = (body: Record<string, unknown>) =>
  apiFetch<Profile>('/api/v1/profile', { method: 'PUT', body: JSON.stringify(body) })
export const deleteAvatar = () => apiFetch<Profile>('/api/v1/profile/avatar', { method: 'DELETE' })

export async function uploadAvatar(file: File): Promise<Profile> {
  const token = await getToken()
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${API_BASE}/api/v1/profile/avatar`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  })
  if (!res.ok) throw new Error(await errorMessage(res, `Upload failed (${res.status})`))
  return res.json() as Promise<Profile>
}

// ── Bank accounts ──────────────────────────────────────────────────────────────

export interface BankAccount {
  id: string
  bank_name: string
  account_type: 'SAVINGS' | 'CURRENT' | 'SALARY'
  last4: string
  nickname?: string | null
  ifsc?: string | null
}
export interface BankAccountSummary extends BankAccount {
  balance: number
  transaction_count: number
  last_transaction_date: string | null
}
export interface BankSummary {
  accounts: BankAccountSummary[]
  total_balance: number
  unassigned: { count: number; balance: number }
}

export const getBankSummary = () => apiFetch<BankSummary>('/api/v1/bank-accounts/summary')
export const listBankAccounts = () => apiFetch<BankAccount[]>('/api/v1/bank-accounts')
export const createBankAccount = (body: Record<string, unknown>) =>
  apiFetch<BankAccount>('/api/v1/bank-accounts', { method: 'POST', body: JSON.stringify(body) })
export const updateBankAccount = (id: string, body: Record<string, unknown>) =>
  apiFetch<BankAccount>(`/api/v1/bank-accounts/${id}`, { method: 'PATCH', body: JSON.stringify(body) })
export const deleteBankAccount = (id: string) => apiFetch<void>(`/api/v1/bank-accounts/${id}`, { method: 'DELETE' })
export const assignUnassigned = (id: string) =>
  apiFetch<{ assigned: number }>(`/api/v1/bank-accounts/${id}/assign-unassigned`, { method: 'POST' })

// ── Credit cards ───────────────────────────────────────────────────────────────

export interface CreditCard {
  id: string
  bank_name: string
  card_name?: string | null
  network?: 'VISA' | 'MASTERCARD' | 'AMEX' | 'RUPAY' | 'DINERS' | 'OTHER' | null
  last4: string
  credit_limit?: number | null
  statement_day?: number | null
  due_day?: number | null
  annual_fee?: number | null
  interest_rate?: number | null
}
export interface CardStatement {
  id: string
  card_id: string
  statement_date: string
  period_start?: string | null
  period_end?: string | null
  due_date?: string | null
  total_due: number
  minimum_due?: number | null
  paid: boolean
  source: string
}
export interface CardDue {
  date: string
  days_left: number
  overdue: boolean
  estimated: boolean
  amount_due: number
  minimum_due: number | null
}
export interface CardOverviewItem {
  card: CreditCard
  credit_limit: number | null
  outstanding: number
  available_credit: number | null
  utilization_pct: number | null
  last_statement: CardStatement | null
  next_due: CardDue | null
  statement_count: number
}
export interface CardsOverview {
  cards: CardOverviewItem[]
  totals: { credit_limit: number; outstanding: number; utilization_pct: number | null }
  upcoming_dues: (CardDue & { card_id: string; label: string })[]
}
export interface CardTxn {
  id: string
  txn_date: string
  description: string
  amount: number
  category?: string | null
}

export const getCardsOverview = () => apiFetch<CardsOverview>('/api/v1/credit-cards/overview')
export const createCreditCard = (body: Record<string, unknown>) =>
  apiFetch<CreditCard>('/api/v1/credit-cards', { method: 'POST', body: JSON.stringify(body) })
export const updateCreditCard = (id: string, body: Record<string, unknown>) =>
  apiFetch<CreditCard>(`/api/v1/credit-cards/${id}`, { method: 'PATCH', body: JSON.stringify(body) })
export const deleteCreditCard = (id: string) => apiFetch<void>(`/api/v1/credit-cards/${id}`, { method: 'DELETE' })
export const listCardStatements = (cardId: string) => apiFetch<CardStatement[]>(`/api/v1/credit-cards/${cardId}/statements`)
export const getStatementTransactions = (id: string) =>
  apiFetch<{ statement: CardStatement; transactions: CardTxn[]; by_category: { category: string; total: number }[] }>(
    `/api/v1/credit-cards/statements/${id}/transactions`,
  )
export const updateCardStatement = (id: string, body: Record<string, unknown>) =>
  apiFetch<CardStatement>(`/api/v1/credit-cards/statements/${id}`, { method: 'PATCH', body: JSON.stringify(body) })
export const deleteCardStatement = (id: string) =>
  apiFetch<void>(`/api/v1/credit-cards/statements/${id}`, { method: 'DELETE' })

export async function importCardStatement(
  cardId: string, file: File, password?: string,
): Promise<{ statement: CardStatement; transactions_inserted: number; duplicates_skipped: number }> {
  const token = await getToken()
  const form = new FormData()
  form.append('file', file)
  if (password) form.append('password', password)
  const res = await fetch(`${API_BASE}/api/v1/credit-cards/${cardId}/statements/import`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  })
  if (!res.ok) throw new Error(await errorMessage(res, `Import failed (${res.status})`))
  return res.json()
}

// ── Import holdings from a brokerage / CAS statement ──────────────────────────

export type HoldingKind = 'STOCK' | 'MF' | 'ETF' | 'BOND' | 'SGB' | 'OTHER'

export interface ImportEntry {
  key: string
  name: string
  symbol: string
  isin: string | null
  holding_type: HoldingKind
  units: number
  avg_buy_price: number | null
  current_price: number | null
  invested: number | null
  current_value: number | null
  action: 'new' | 'update' | 'unchanged'
  existing_id: string | null
  changes: Record<string, { from: number | null; to: number | null }>
}

export interface ImportPreview {
  source: string
  entries: ImportEntry[]
  missing: { id: string; name: string | null; symbol: string | null; units: number | null }[]
  warnings: string[]
  counts: { new: number; update: number; unchanged: number }
  totals: { invested: number; current_value: number }
}

export async function previewHoldingsImport(file: File, source?: string, password?: string): Promise<ImportPreview> {
  const token = await getToken()
  const form = new FormData()
  form.append('file', file)
  if (source) form.append('source', source)
  if (password) form.append('password', password)
  const res = await fetch(`${API_BASE}/api/v1/investments/import/preview`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  })
  if (!res.ok) throw new Error(await errorMessage(res, `Could not read the statement (${res.status})`))
  return res.json() as Promise<ImportPreview>
}

export interface ConfirmRowBody {
  name: string
  symbol: string
  isin: string | null
  holding_type: HoldingKind
  units: number
  avg_buy_price: number | null
  current_price: number | null
  existing_id: string | null
}

export const confirmHoldingsImport = (body: { source: string; rows: ConfirmRowBody[]; remove_ids: string[]; assumed_buy_date?: string }) =>
  apiFetch<{ inserted: number; updated: number; removed: number; assumed_lots: number }>('/api/v1/investments/import/confirm', {
    method: 'POST',
    body: JSON.stringify(body),
  })

// ── Feedback (becomes a GitHub issue) ─────────────────────────────────────────

export type FeedbackKind = 'issue' | 'idea' | 'question'

export function submitFeedback(kind: FeedbackKind, message: string, page?: string): Promise<{ ok: boolean; issue_number: number }> {
  return apiFetch('/api/v1/feedback', { method: 'POST', body: JSON.stringify({ kind, message, page }) })
}
