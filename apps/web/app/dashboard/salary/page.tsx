'use client'

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'

import DashboardNav from '@/components/dashboard/DashboardNav'
import { createSalary, deleteSalary, listSalary, updateSalary, type SalaryRecord } from '@/lib/api'
import { formatINR } from '@/lib/format'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const money = (n?: number | null) => (n == null ? '—' : formatINR(n))

type Row = SalaryRecord & { special_allowance?: number | null; pf_employer?: number | null }

const AMOUNT_FIELDS: { name: keyof Row; label: string }[] = [
  { name: 'gross_pay', label: 'Gross pay' },
  { name: 'net_pay', label: 'Net pay' },
  { name: 'basic', label: 'Basic' },
  { name: 'hra', label: 'HRA' },
  { name: 'special_allowance', label: 'Special allowance' },
  { name: 'pf_employee', label: 'PF (employee)' },
  { name: 'pf_employer', label: 'PF (employer)' },
  { name: 'income_tax', label: 'Income tax (TDS)' },
  { name: 'professional_tax', label: 'Professional tax' },
]

const today = new Date()
const blank = { month: String(today.getMonth() + 1), year: String(today.getFullYear()), employer_name: '' } as Record<string, string>

export default function SalaryPage() {
  const [rows, setRows] = useState<Row[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<string | 'new' | null>(null)
  const [form, setForm] = useState<Record<string, string>>(blank)
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    try {
      setRows((await listSalary()) as Row[])
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  function startEdit(r: Row) {
    const f: Record<string, string> = { month: String(r.month), year: String(r.year), employer_name: r.employer_name ?? '' }
    for (const a of AMOUNT_FIELDS) f[a.name as string] = r[a.name] == null ? '' : String(r[a.name])
    setForm(f)
    setEditing(r.id)
    setError(null)
  }

  function startNew() {
    setForm(blank)
    setEditing('new')
    setError(null)
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    const body: Record<string, unknown> = { month: Number(form.month), year: Number(form.year), employer_name: form.employer_name || null }
    for (const a of AMOUNT_FIELDS) {
      const v = form[a.name as string]
      // On edit an emptied box clears the value; on create it is simply omitted.
      if (v !== undefined && v !== '') body[a.name as string] = Number(v)
      else if (editing !== 'new') body[a.name as string] = null
    }
    setSaving(true)
    try {
      if (editing === 'new') await createSalary(body)
      else if (editing) await updateSalary(editing, body)
      setEditing(null)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  async function onDelete(id: string) {
    try {
      await deleteSalary(id)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete')
    }
  }

  // API returns newest first; chart wants oldest first, last 12 months.
  const chart = [...rows].reverse().slice(-12)
  const maxNet = Math.max(1, ...chart.map((r) => r.net_pay ?? 0))
  const latest = rows[0]
  const input = 'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500'

  return (
    <div className="min-h-screen bg-slate-50">
      <DashboardNav active="/dashboard/salary" />
      <main className="max-w-6xl mx-auto px-6 py-8 space-y-6">
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">Salary</h1>
            <p className="text-sm text-slate-500 mt-0.5">Payslips you have saved, month by month. Add or correct any month by hand.</p>
          </div>
          <div className="flex gap-2">
            <button onClick={startNew} className="rounded-lg border border-slate-300 bg-white text-sm font-medium px-4 py-2 hover:border-indigo-300">
              Add month
            </button>
            <Link href="/dashboard/upload" className="rounded-lg bg-indigo-600 text-white text-sm font-medium px-4 py-2 hover:bg-indigo-700">
              Upload payslip
            </Link>
          </div>
        </div>

        {error && <p className="text-sm text-red-500">{error}</p>}

        {editing && (
          <form onSubmit={onSubmit} className="bg-white rounded-2xl border border-indigo-200 p-6 space-y-4">
            <h2 className="text-sm font-semibold text-slate-900">{editing === 'new' ? 'Add a salary month' : 'Edit salary record'}</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <label className="text-xs text-slate-600 space-y-1">
                <span>Month</span>
                <select className={input} value={form.month} onChange={(e) => setForm({ ...form, month: e.target.value })}>
                  {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
                </select>
              </label>
              <label className="text-xs text-slate-600 space-y-1">
                <span>Year</span>
                <input className={input} type="number" min={2000} max={2100} required value={form.year} onChange={(e) => setForm({ ...form, year: e.target.value })} />
              </label>
              <label className="text-xs text-slate-600 space-y-1 col-span-2">
                <span>Employer</span>
                <input className={input} value={form.employer_name} onChange={(e) => setForm({ ...form, employer_name: e.target.value })} />
              </label>
              {AMOUNT_FIELDS.map((a) => (
                <label key={a.name} className="text-xs text-slate-600 space-y-1">
                  <span>{a.label} (₹)</span>
                  <input className={input} type="number" step="any" value={form[a.name as string] ?? ''} onChange={(e) => setForm({ ...form, [a.name as string]: e.target.value })} />
                </label>
              ))}
            </div>
            <div className="flex gap-2">
              <button type="submit" disabled={saving} className="rounded-lg bg-indigo-600 text-white text-sm font-medium px-4 py-2 hover:bg-indigo-700 disabled:opacity-50">
                {saving ? 'Saving…' : 'Save'}
              </button>
              <button type="button" onClick={() => setEditing(null)} className="rounded-lg border border-slate-300 text-sm px-4 py-2 text-slate-600">Cancel</button>
            </div>
          </form>
        )}

        {loading ? (
          <p className="text-sm text-slate-400">Loading…</p>
        ) : rows.length === 0 ? (
          <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center">
            <p className="text-sm text-slate-500">No salary records yet.</p>
            <p className="text-xs text-slate-400 mt-1">Upload a payslip, or use “Add month” to enter one by hand.</p>
          </div>
        ) : (
          <>
            {latest && (
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {[
                  ['Latest month', `${MONTHS[latest.month - 1]} ${latest.year}`],
                  ['Gross pay', money(latest.gross_pay)],
                  ['Net pay', money(latest.net_pay)],
                  ['Income tax (TDS)', money(latest.income_tax)],
                ].map(([label, value]) => (
                  <div key={label} className="bg-white rounded-2xl border border-slate-200 p-5">
                    <p className="text-xs text-slate-500 uppercase tracking-wide">{label}</p>
                    <p className="text-xl font-semibold text-slate-900 mt-1">{value}</p>
                  </div>
                ))}
              </div>
            )}

            <section className="bg-white rounded-2xl border border-slate-200 p-6">
              <h2 className="text-sm font-semibold text-slate-900 mb-4">Net pay by month</h2>
              <div className="flex items-end gap-2 h-40">
                {chart.map((r) => (
                  <div key={r.id} className="flex-1 flex flex-col items-center justify-end h-full gap-1" title={`${MONTHS[r.month - 1]} ${r.year}: ${money(r.net_pay)}`}>
                    <div className="w-full bg-indigo-500 rounded-t" style={{ height: `${((r.net_pay ?? 0) / maxNet) * 100}%` }} />
                    <span className="text-[10px] text-slate-400">{MONTHS[r.month - 1]}</span>
                  </div>
                ))}
              </div>
            </section>

            <section className="bg-white rounded-2xl border border-slate-200 p-6 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-500 border-b border-slate-100">
                    <th className="py-2 pr-4 font-medium">Month</th>
                    <th className="py-2 pr-4 font-medium">Employer</th>
                    <th className="py-2 pr-4 font-medium text-right">Basic</th>
                    <th className="py-2 pr-4 font-medium text-right">HRA</th>
                    <th className="py-2 pr-4 font-medium text-right">PF</th>
                    <th className="py-2 pr-4 font-medium text-right">Tax</th>
                    <th className="py-2 pr-4 font-medium text-right">Gross</th>
                    <th className="py-2 pr-4 font-medium text-right">Net</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id} className="border-b border-slate-50">
                      <td className="py-2 pr-4 whitespace-nowrap">{MONTHS[r.month - 1]} {r.year}</td>
                      <td className="py-2 pr-4 text-slate-600 max-w-[14rem] truncate">{r.employer_name ?? '—'}</td>
                      <td className="py-2 pr-4 text-right">{money(r.basic)}</td>
                      <td className="py-2 pr-4 text-right">{money(r.hra)}</td>
                      <td className="py-2 pr-4 text-right">{money(r.pf_employee)}</td>
                      <td className="py-2 pr-4 text-right">{money(r.income_tax)}</td>
                      <td className="py-2 pr-4 text-right">{money(r.gross_pay)}</td>
                      <td className="py-2 pr-4 text-right font-medium">{money(r.net_pay)}</td>
                      <td className="py-2 text-right whitespace-nowrap">
                        <button onClick={() => startEdit(r)} className="text-xs text-indigo-600 hover:text-indigo-800 mr-3">Edit</button>
                        <button onClick={() => onDelete(r.id)} className="text-xs text-red-500 hover:text-red-700">Delete</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </>
        )}
      </main>
    </div>
  )
}
