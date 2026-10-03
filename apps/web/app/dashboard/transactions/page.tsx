'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

import DashboardNav from '@/components/dashboard/DashboardNav'
import {
  deleteTransaction, getMonthlySummary, importStatement, listCategories, listTransactions,
  updateTransactionCategory,
  type MonthlySummary, type Transaction,
} from '@/lib/api'
import { formatINR } from '@/lib/format'

function currentMonth() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

export default function TransactionsPage() {
  const [month, setMonth] = useState(currentMonth())
  const [category, setCategory] = useState('')
  const [categories, setCategories] = useState<string[]>([])
  const [txns, setTxns] = useState<Transaction[]>([])
  const [summary, setSummary] = useState<MonthlySummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [importMsg, setImportMsg] = useState<string | null>(null)
  const [importing, setImporting] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [t, s] = await Promise.all([
        listTransactions(month, category || undefined),
        getMonthlySummary(month),
      ])
      setTxns(t)
      setSummary(s)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [month, category])

  useEffect(() => { load() }, [load])
  useEffect(() => { listCategories().then(setCategories).catch(() => {}) }, [])

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setImporting(true)
    setImportMsg(null)
    try {
      const r = await importStatement(file)
      setImportMsg(`Imported ${r.inserted} of ${r.parsed} transactions (${r.duplicates_skipped} duplicates skipped).`)
      await load()
    } catch (err) {
      setImportMsg(err instanceof Error ? err.message : 'Import failed')
    } finally {
      setImporting(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  async function onRecategorise(id: string, cat: string) {
    try {
      await updateTransactionCategory(id, cat)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update')
    }
  }

  async function onDelete(id: string) {
    try {
      await deleteTransaction(id)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete')
    }
  }

  const maxCat = Math.max(1, ...(summary?.by_category.map((c) => c.total) ?? [1]))

  return (
    <div className="min-h-screen bg-slate-50">
      <DashboardNav active="/dashboard/transactions" />
      <main className="max-w-6xl mx-auto px-6 py-8 space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">Transactions</h1>
            <p className="text-sm text-slate-500 mt-0.5">Import a bank statement (CSV, PDF or image) — rows are auto-categorised.</p>
          </div>
          <div className="flex items-center gap-3">
            <input
              type="month"
              value={month}
              onChange={(e) => e.target.value && setMonth(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            <input ref={fileRef} type="file" accept=".csv,.pdf,image/*" onChange={onFile} className="hidden" />
            <button
              onClick={() => fileRef.current?.click()}
              disabled={importing}
              className="rounded-lg bg-indigo-600 text-white text-sm font-medium px-4 py-2 hover:bg-indigo-700 disabled:opacity-50"
            >
              {importing ? 'Importing…' : 'Import statement'}
            </button>
          </div>
        </div>

        {importMsg && <p className="text-sm text-slate-600 bg-white border border-slate-200 rounded-lg px-4 py-2">{importMsg}</p>}
        {error && <p className="text-sm text-red-500">{error}</p>}

        {summary && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="bg-white rounded-2xl border border-slate-200 p-6 space-y-3">
              <h2 className="text-sm font-semibold text-slate-900">Cash flow</h2>
              <div className="flex justify-between text-sm"><span className="text-slate-500">In</span><span className="text-green-600 font-medium">{formatINR(summary.income)}</span></div>
              <div className="flex justify-between text-sm"><span className="text-slate-500">Out</span><span className="text-red-600 font-medium">{formatINR(summary.expenses)}</span></div>
              <div className="flex justify-between text-sm border-t border-slate-100 pt-3"><span className="text-slate-500">Net</span><span className="font-semibold">{summary.net < 0 ? '-' : ''}{formatINR(summary.net)}</span></div>
            </div>
            <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 p-6">
              <h2 className="text-sm font-semibold text-slate-900 mb-4">Spend by category</h2>
              {summary.by_category.length === 0 ? (
                <p className="text-sm text-slate-400">No spending this month.</p>
              ) : (
                <ul className="space-y-2">
                  {summary.by_category.map((c) => (
                    <li key={c.category} className="text-sm">
                      <div className="flex justify-between"><span className="text-slate-700">{c.category}</span><span className="text-slate-900">{formatINR(c.total)}</span></div>
                      <div className="h-1.5 bg-slate-100 rounded-full mt-1"><div className="h-1.5 bg-indigo-500 rounded-full" style={{ width: `${(c.total / maxCat) * 100}%` }} /></div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}

        <section className="bg-white rounded-2xl border border-slate-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-slate-900">Transactions</h2>
            <select value={category} onChange={(e) => setCategory(e.target.value)} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm">
              <option value="">All categories</option>
              {categories.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          {loading ? (
            <p className="text-sm text-slate-400">Loading…</p>
          ) : txns.length === 0 ? (
            <p className="text-sm text-slate-400">No transactions for this month.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-500 border-b border-slate-100">
                    <th className="py-2 pr-4 font-medium">Date</th>
                    <th className="py-2 pr-4 font-medium">Description</th>
                    <th className="py-2 pr-4 font-medium">Category</th>
                    <th className="py-2 pr-4 font-medium text-right">Amount</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {txns.map((t) => (
                    <tr key={t.id} className="border-b border-slate-50">
                      <td className="py-2 pr-4 whitespace-nowrap text-slate-600">{t.transaction_date}</td>
                      <td className="py-2 pr-4 text-slate-800 max-w-xs truncate">{t.description}</td>
                      <td className="py-2 pr-4">
                        <select
                          value={t.category ?? 'Other'}
                          onChange={(e) => onRecategorise(t.id, e.target.value)}
                          className="rounded border border-slate-200 px-2 py-1 text-xs bg-white"
                        >
                          {[...categories, ...(t.category && !categories.includes(t.category) ? [t.category] : [])].map((c) => <option key={c} value={c}>{c}</option>)}
                        </select>
                      </td>
                      <td className={`py-2 pr-4 text-right whitespace-nowrap font-medium ${t.amount < 0 ? 'text-red-600' : 'text-green-600'}`}>
                        {t.amount < 0 ? '-' : '+'}{formatINR(t.amount)}
                      </td>
                      <td className="py-2 text-right"><button onClick={() => onDelete(t.id)} className="text-xs text-red-500 hover:text-red-700">Delete</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>
    </div>
  )
}
