import { createClient } from '@/lib/supabase'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

async function getToken(): Promise<string> {
  const { data: { session } } = await createClient().auth.getSession()
  if (!session) throw new Error('Not authenticated')
  return session.access_token
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
    const body = await res.json().catch(() => ({})) as { detail?: string }
    throw new Error(body.detail ?? `Request failed (${res.status})`)
  }
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
