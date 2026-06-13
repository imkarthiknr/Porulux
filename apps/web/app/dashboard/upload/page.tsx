'use client'

import Link from 'next/link'
import { useCallback, useRef, useState } from 'react'

import { formatINR } from '@/lib/format'
import { savePayslip, uploadDocument, type DocType, type UploadResult } from '@/lib/api'

// ── Types ──────────────────────────────────────────────────────────────────────

type Stage = 'idle' | 'uploading' | 'done' | 'error'

// ── Constants ──────────────────────────────────────────────────────────────────

const DOC_TYPES: { value: DocType; label: string }[] = [
  { value: 'auto', label: 'Auto-detect' },
  { value: 'payslip', label: 'Payslip' },
  { value: 'bank_statement', label: 'Bank Statement' },
  { value: 'form16', label: 'Form 16' },
  { value: 'cas_statement', label: 'CAS Statement' },
]

const DOC_TYPE_LABELS: Record<string, string> = {
  payslip: 'Payslip',
  bank_statement: 'Bank Statement',
  form16: 'Form 16',
  cas_statement: 'CAS Statement',
  unknown: 'Unknown Document',
}

const FIELD_LABELS: Record<string, string> = {
  month: 'Month',
  employer: 'Employer',
  employee_name: 'Employee',
  gross_salary: 'Gross Salary',
  basic: 'Basic',
  hra: 'HRA',
  pf_employee: 'PF (Employee)',
  pf_employer: 'PF (Employer)',
  professional_tax: 'Professional Tax',
  tds: 'TDS',
  net_salary: 'Net Salary',
  total_deductions: 'Total Deductions',
  bank_name: 'Bank',
  account_number: 'Account (last 4)',
  period_start: 'Period Start',
  period_end: 'Period End',
  opening_balance: 'Opening Balance',
  closing_balance: 'Closing Balance',
  total_credits: 'Total Credits',
  total_debits: 'Total Debits',
  transaction_count: 'Transactions',
  financial_year: 'Financial Year',
  pan: 'PAN',
  exempt_allowances: 'Exempt Allowances',
  net_taxable_salary: 'Net Taxable Salary',
  total_income: 'Total Income',
  total_deductions_80c: 'Deductions (80C+)',
  taxable_income: 'Taxable Income',
  tax_payable: 'Tax Payable',
  tds_deducted: 'TDS Deducted',
  investor_name: 'Investor',
  total_portfolio_value: 'Portfolio Value',
  total_invested: 'Total Invested',
  total_gains: 'Unrealised Gains',
  folio_count: 'Folios',
  scheme_count: 'Schemes',
}

const CURRENCY_FIELDS = new Set([
  'gross_salary', 'basic', 'hra', 'pf_employee', 'pf_employer',
  'professional_tax', 'tds', 'net_salary', 'total_deductions',
  'opening_balance', 'closing_balance', 'total_credits', 'total_debits',
  'exempt_allowances', 'net_taxable_salary', 'total_income', 'total_deductions_80c',
  'taxable_income', 'tax_payable', 'tds_deducted',
  'total_portfolio_value', 'total_invested', 'total_gains',
])

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmtValue(key: string, value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (CURRENCY_FIELDS.has(key) && typeof value === 'number') return formatINR(value)
  return String(value)
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function UploadIcon() {
  return (
    <svg className="w-10 h-10 text-indigo-400" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5" />
    </svg>
  )
}

function ExtractionPreview({ result }: { result: UploadResult }) {
  const label = DOC_TYPE_LABELS[result.doc_type] ?? result.doc_type
  const entries = Object.entries(result.data).filter(
    ([k, v]) => k !== 'doc_type' && v !== null && v !== undefined,
  )

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-700">
          {label}
        </span>
        {result.confidence && (
          <span className={`text-xs font-medium ${result.confidence === 'high' ? 'text-emerald-600' : 'text-amber-500'}`}>
            {result.confidence === 'high' ? '● High confidence' : '● Low confidence'}
          </span>
        )}
      </div>

      {entries.length > 0 ? (
        <dl className="grid grid-cols-2 gap-x-8 gap-y-4">
          {entries.map(([key, value]) => (
            <div key={key}>
              <dt className="text-xs font-medium text-slate-400 uppercase tracking-wide">
                {FIELD_LABELS[key] ?? key}
              </dt>
              <dd className="text-sm font-semibold text-slate-900 mt-0.5 tabular-nums">
                {fmtValue(key, value)}
              </dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="text-sm text-slate-400">
          {result.doc_type === 'unknown'
            ? 'Could not identify this document type. Try selecting a specific type above.'
            : 'No fields could be extracted from this document.'}
        </p>
      )}
    </div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function UploadPage() {
  const [docType, setDocType] = useState<DocType>('auto')
  const [stage, setStage] = useState<Stage>('idle')
  const [progress, setProgress] = useState(0)
  const [result, setResult] = useState<UploadResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = useCallback(
    async (file: File) => {
      setStage('uploading')
      setProgress(0)
      setResult(null)
      setError(null)
      setSaveState('idle')
      setSaveError(null)

      try {
        const res = await uploadDocument(file, docType, (pct) => setProgress(pct))
        setResult(res)
        setStage('done')
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Upload failed')
        setStage('error')
      }
    },
    [docType],
  )

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragOver(false)
      const file = e.dataTransfer.files[0]
      if (file) handleFile(file)
    },
    [handleFile],
  )

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) handleFile(file)
    },
    [handleFile],
  )

  const handleSave = async () => {
    if (!result) return
    setSaveState('saving')
    setSaveError(null)

    try {
      if (result.doc_type === 'payslip') {
        await savePayslip(result.data)
      }
      setSaveState('saved')
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Save failed')
      setSaveState('error')
    }
  }

  const handleReset = () => {
    setStage('idle')
    setResult(null)
    setError(null)
    setSaveState('idle')
    setSaveError(null)
    setProgress(0)
    if (inputRef.current) inputRef.current.value = ''
  }

  const canSave = result && result.doc_type !== 'unknown' && Object.keys(result.data).length > 0

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center justify-between">
          <span className="text-lg font-bold text-indigo-600 tracking-tight">₹ Porulux</span>
          <Link
            href="/dashboard"
            className="text-sm text-slate-500 hover:text-slate-800 transition-colors"
          >
            ← Dashboard
          </Link>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-10 space-y-8">
        {/* Title */}
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Upload Document</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            AI-powered extraction for payslips, bank statements, Form 16, and CAS statements.
          </p>
        </div>

        {/* Doc type selector */}
        <div className="flex gap-2 flex-wrap">
          {DOC_TYPES.map((t) => (
            <button
              key={t.value}
              onClick={() => setDocType(t.value)}
              disabled={stage === 'uploading'}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                docType === t.value
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'bg-white border border-slate-200 text-slate-600 hover:border-indigo-300 hover:text-indigo-600'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Drop zone — visible when idle or after an error */}
        {(stage === 'idle' || stage === 'error') && (
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => inputRef.current?.click()}
            className={`border-2 border-dashed rounded-2xl p-14 text-center cursor-pointer transition-colors ${
              dragOver
                ? 'border-indigo-400 bg-indigo-50'
                : 'border-slate-300 bg-white hover:border-indigo-300 hover:bg-indigo-50/30'
            }`}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,.webp,.csv"
              onChange={handleChange}
              className="hidden"
            />
            <div className="flex flex-col items-center gap-3">
              <UploadIcon />
              <div>
                <p className="text-sm font-semibold text-slate-700">
                  Drop your file here, or click to browse
                </p>
                <p className="text-xs text-slate-400 mt-1">PDF, JPEG, PNG, WebP, CSV — up to 20 MB</p>
              </div>
            </div>
            {stage === 'error' && error && (
              <p className="mt-5 text-sm font-medium text-red-600 bg-red-50 px-4 py-2 rounded-lg inline-block">
                {error}
              </p>
            )}
          </div>
        )}

        {/* Progress */}
        {stage === 'uploading' && (
          <div className="bg-white border border-slate-200 rounded-2xl p-8 space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-5 h-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
              <p className="text-sm font-medium text-slate-700">Extracting data with AI…</p>
            </div>
            <div className="w-full bg-slate-100 rounded-full h-1.5 overflow-hidden">
              <div
                className="bg-indigo-500 h-1.5 rounded-full transition-all duration-300"
                style={{ width: `${progress < 100 ? progress : 90}%` }}
              />
            </div>
            <p className="text-xs text-slate-400">
              {progress < 100 ? `Uploading… ${progress}%` : 'Processing with Claude…'}
            </p>
          </div>
        )}

        {/* Result panel */}
        {stage === 'done' && result && (
          <div className="bg-white border border-slate-200 rounded-2xl divide-y divide-slate-100">
            <div className="p-6 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-900">Extracted Data</h2>
              <button
                onClick={handleReset}
                className="text-xs text-slate-400 hover:text-slate-600 transition-colors"
              >
                Upload another
              </button>
            </div>

            <div className="p-6">
              <ExtractionPreview result={result} />
            </div>

            <div className="p-6">
              {saveState === 'saved' ? (
                <div className="flex items-center gap-2 text-sm font-medium text-emerald-600">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                  </svg>
                  Saved to Porulux
                </div>
              ) : (
                <div className="space-y-2">
                  <button
                    onClick={handleSave}
                    disabled={!canSave || saveState === 'saving'}
                    className="w-full py-2.5 px-4 bg-indigo-600 text-white text-sm font-semibold rounded-xl hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {saveState === 'saving' ? 'Saving…' : 'Save to Porulux'}
                  </button>
                  {saveState === 'error' && saveError && (
                    <p className="text-xs text-red-500">{saveError}</p>
                  )}
                  {result.doc_type !== 'payslip' && result.doc_type !== 'unknown' && (
                    <p className="text-xs text-slate-400 text-center">
                      Direct save for {DOC_TYPE_LABELS[result.doc_type] ?? result.doc_type} coming soon.
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
