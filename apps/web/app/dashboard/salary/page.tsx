'use client'

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'

import DashboardNav from '@/components/dashboard/DashboardNav'
import { deleteSalary, listSalary, type SalaryRecord } from '@/lib/api'
import { formatINR } from '@/lib/format'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const money = (n?: number | null) => (n == null ? '—' : formatINR(n))

export default function SalaryPage() {
  const [rows, setRows] = useState<SalaryRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setRows(await listSalary())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

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

  return (
    <div className="min-h-screen bg-slate-50">
      <DashboardNav active="/dashboard/salary" />
      <main className="max-w-6xl mx-auto px-6 py-8 space-y-6">
        <div className="flex items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">Salary</h1>
            <p className="text-sm text-slate-500 mt-0.5">Payslips you have saved, month by month.</p>
          </div>
          <Link href="/dashboard/upload" className="rounded-lg bg-indigo-600 text-white text-sm font-medium px-4 py-2 hover:bg-indigo-700">
            Upload payslip
          </Link>
        </div>

        {error && <p className="text-sm text-red-500">{error}</p>}

        {loading ? (
          <p className="text-sm text-slate-400">Loading…</p>
        ) : rows.length === 0 ? (
          <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center">
            <p className="text-sm text-slate-500">No payslips saved yet.</p>
            <p className="text-xs text-slate-400 mt-1">Upload one, then click “Save to Porulux” on the review screen.</p>
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
                      <td className="py-2 text-right"><button onClick={() => onDelete(r.id)} className="text-xs text-red-500 hover:text-red-700">Delete</button></td>
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
