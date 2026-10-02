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

export const listTransactions = (month: string, category?: string) =>
  apiFetch<Transaction[]>(
    `/api/v1/transactions/?month=${month}${category ? `&category=${encodeURIComponent(category)}` : ''}`,
  )
export const getMonthlySummary = (month: string) =>
  apiFetch<MonthlySummary>(`/api/v1/transactions/summary?month=${month}`)
export const listCategories = () => apiFetch<string[]>('/api/v1/transactions/categories')
export const createTransaction = (body: Record<string, unknown>) =>
  apiFetch<Transaction>('/api/v1/transactions/', { method: 'POST', body: JSON.stringify(body) })
export const updateTransactionCategory = (id: string, category: string) =>
  apiFetch<Transaction>(`/api/v1/transactions/${id}`, { method: 'PATCH', body: JSON.stringify({ category }) })
export const deleteTransaction = (id: string) =>
  apiFetch<void>(`/api/v1/transactions/${id}`, { method: 'DELETE' })

export async function importStatement(file: File, bankName?: string): Promise<ImportResult> {
  const token = await getToken()
  const form = new FormData()
  form.append('file', file)
  if (bankName) form.append('bank_name', bankName)
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
