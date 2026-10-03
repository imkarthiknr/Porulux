'use client'

import { useCallback, useEffect, useState } from 'react'

import DashboardNav from '@/components/dashboard/DashboardNav'
import {
  createItem, deleteItem, listItems,
  type EpfNps, type Holding, type Loan, type Resource,
} from '@/lib/api'
import { formatINR } from '@/lib/format'

// ── Section config ─────────────────────────────────────────────────────────────

interface Field {
  name: string
  label: string
  type?: 'text' | 'number' | 'date'
  options?: string[]
  required?: boolean
}

interface SectionConfig<T> {
  resource: Resource
  title: string
  blurb: string
  fields: Field[]
  columns: { label: string; render: (row: T) => string }[]
}

const HOLDING_TYPES = ['STOCK', 'MF', 'ETF', 'BOND', 'SGB', 'OTHER']
const LOAN_TYPES = ['HOME_LOAN', 'PERSONAL_LOAN', 'VEHICLE_LOAN', 'CREDIT_CARD', 'OTHER']
const ACCOUNT_TYPES = ['EPF', 'NPS_TIER1', 'NPS_TIER2']

const holdingsConfig: SectionConfig<Holding> = {
  resource: 'holdings',
  title: 'Investments',
  blurb: 'Stocks, mutual funds, ETFs, bonds. Value = units × current price.',
  fields: [
    { name: 'symbol', label: 'Symbol', required: true },
    { name: 'name', label: 'Name', required: true },
    { name: 'holding_type', label: 'Type', options: HOLDING_TYPES, required: true },
    { name: 'units', label: 'Units', type: 'number', required: true },
    { name: 'current_price', label: 'Current price (₹)', type: 'number' },
    { name: 'avg_buy_price', label: 'Avg buy price (₹)', type: 'number' },
  ],
  columns: [
    { label: 'Name', render: (h) => `${h.name} (${h.symbol})` },
    { label: 'Type', render: (h) => h.holding_type },
    { label: 'Units', render: (h) => String(h.units) },
    { label: 'Value', render: (h) => formatINR(h.units * (h.current_price ?? 0)) },
  ],
}

const loansConfig: SectionConfig<Loan> = {
  resource: 'loans',
  title: 'Loans & Liabilities',
  blurb: 'Home loan, personal loan, vehicle loan, credit card dues. Fill amount, rate, tenure and start date to unlock the EMI schedule and tax benefit on the Loans page.',
  fields: [
    { name: 'loan_type', label: 'Type', options: LOAN_TYPES, required: true },
    { name: 'lender_name', label: 'Lender' },
    { name: 'outstanding_amount', label: 'Outstanding (₹)', type: 'number', required: true },
    { name: 'emi_amount', label: 'EMI (₹)', type: 'number' },
    { name: 'interest_rate', label: 'Interest rate (%)', type: 'number' },
    { name: 'principal_amount', label: 'Original amount (₹)', type: 'number' },
    { name: 'tenure_months', label: 'Tenure (months)', type: 'number' },
    { name: 'start_date', label: 'Start date', type: 'date' },
  ],
  columns: [
    { label: 'Type', render: (l) => l.loan_type.replace('_', ' ') },
    { label: 'Lender', render: (l) => l.lender_name ?? '—' },
    { label: 'EMI', render: (l) => (l.emi_amount ? formatINR(l.emi_amount) : '—') },
    { label: 'Outstanding', render: (l) => formatINR(l.outstanding_amount) },
  ],
}

const epfConfig: SectionConfig<EpfNps> = {
  resource: 'epf-nps',
  title: 'EPF & NPS',
  blurb: 'Provident fund and pension balances.',
  fields: [
    { name: 'account_type', label: 'Account', options: ACCOUNT_TYPES, required: true },
    { name: 'balance', label: 'Balance (₹)', type: 'number', required: true },
    { name: 'as_of_date', label: 'As of', type: 'date' },
  ],
  columns: [
    { label: 'Account', render: (a) => a.account_type.replace('_', ' ') },
    { label: 'As of', render: (a) => a.as_of_date },
    { label: 'Balance', render: (a) => formatINR(a.balance) },
  ],
}

// ── Generic section ────────────────────────────────────────────────────────────

function Section<T extends { id: string }>({ config }: { config: SectionConfig<T> }) {
  const [rows, setRows] = useState<T[]>([])
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    try {
      setRows(await listItems<T>(config.resource))
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [config.resource])

  useEffect(() => { load() }, [load])

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    const body: Record<string, unknown> = {}
    for (const f of config.fields) {
      const v = form[f.name]
      if (v === undefined || v === '') continue
      body[f.name] = f.type === 'number' ? Number(v) : v
    }
    for (const f of config.fields) {
      if (f.options && body[f.name] === undefined) body[f.name] = f.options[0]
    }
    setSaving(true)
    try {
      await createItem<T>(config.resource, body)
      setForm({})
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  async function onDelete(id: string) {
    try {
      await deleteItem(config.resource, id)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete')
    }
  }

  const input = 'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500'

  return (
    <section className="bg-white rounded-2xl border border-slate-200 p-6">
      <h2 className="text-sm font-semibold text-slate-900">{config.title}</h2>
      <p className="text-xs text-slate-500 mt-0.5 mb-4">{config.blurb}</p>

      {error && <p className="text-xs text-red-500 mb-3">{error}</p>}

      {loading ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-slate-400 mb-4">Nothing added yet.</p>
      ) : (
        <div className="overflow-x-auto mb-5">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500 border-b border-slate-100">
                {config.columns.map((c) => <th key={c.label} className="py-2 pr-4 font-medium">{c.label}</th>)}
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-b border-slate-50">
                  {config.columns.map((c) => <td key={c.label} className="py-2 pr-4 text-slate-800">{c.render(row)}</td>)}
                  <td className="py-2 text-right">
                    <button onClick={() => onDelete(row.id)} className="text-xs text-red-500 hover:text-red-700">Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <form onSubmit={onSubmit} className="grid grid-cols-2 md:grid-cols-3 gap-3 items-end">
        {config.fields.map((f) => (
          <label key={f.name} className="text-xs text-slate-600 space-y-1">
            <span>{f.label}</span>
            {f.options ? (
              <select
                className={input}
                value={form[f.name] ?? f.options[0]}
                onChange={(e) => setForm({ ...form, [f.name]: e.target.value })}
              >
                {f.options.map((o) => <option key={o} value={o}>{o.replace('_', ' ')}</option>)}
              </select>
            ) : (
              <input
                className={input}
                type={f.type ?? 'text'}
                step={f.type === 'number' ? 'any' : undefined}
                min={f.type === 'number' ? 0 : undefined}
                required={f.required}
                value={form[f.name] ?? ''}
                onChange={(e) => setForm({ ...form, [f.name]: e.target.value })}
              />
            )}
          </label>
        ))}
        <button
          type="submit"
          disabled={saving}
          className="rounded-lg bg-indigo-600 text-white text-sm font-medium px-4 py-2 hover:bg-indigo-700 disabled:opacity-50"
        >
          {saving ? 'Adding…' : 'Add'}
        </button>
      </form>
    </section>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function AccountsPage() {
  return (
    <div className="min-h-screen bg-slate-50">
      <DashboardNav active="/dashboard/accounts" />
      <main className="max-w-6xl mx-auto px-6 py-8 space-y-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Accounts</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Enter your holdings, loans and EPF/NPS balances — they feed your net worth.
          </p>
        </div>
        <Section config={holdingsConfig} />
        <Section config={epfConfig} />
        <Section config={loansConfig} />
      </main>
    </div>
  )
}
