'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

import DashboardNav from '@/components/dashboard/DashboardNav'
import AIKeyBanner from '@/components/dashboard/AIKeyBanner'
import RecurringPayments from '@/components/dashboard/RecurringPayments'
import SpendTrendChart from '@/components/dashboard/SpendTrendChart'
import {
  cleanKeyMessage, cleanPasswordMessage, isKeyError, isPasswordError,
  createTransaction, deleteTransaction, listBankAccounts, getMonthlySummary, importStatement, listCategories, listTransactions,
  updateTransaction, updateTransactionCategory,
  type BankAccount, type MonthlySummary, type Transaction,
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
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [accounts, setAccounts] = useState<BankAccount[]>([])
  const [accountId, setAccountId] = useState('')   // '' = all, 'unassigned', or an account id
  const [editing, setEditing] = useState<string | 'new' | null>(null)
  const [form, setForm] = useState({ date: '', description: '', amount: '', kind: 'debit', category: '', account_id: '' })
  const [saving, setSaving] = useState(false)
  const [password, setPassword] = useState('')
  const [needsPassword, setNeedsPassword] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [t, s] = await Promise.all([
        listTransactions(month, category || undefined, accountId || undefined),
        getMonthlySummary(month, accountId || undefined),
      ])
      setTxns(t)
      setSummary(s)
      setRefreshKey((k) => k + 1)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [month, category, accountId])

  useEffect(() => { load() }, [load])
  useEffect(() => { listCategories().then(setCategories).catch(() => {}) }, [])
  useEffect(() => {
    listBankAccounts().then(setAccounts).catch(() => {})
    const fromUrl = new URLSearchParams(window.location.search).get('account')
    if (fromUrl) setAccountId(fromUrl)
  }, [])

  async function runImport(file: File, pw?: string) {
    setImporting(true)
    setImportMsg(null)
    try {
      const r = await importStatement(file, undefined, pw, accountId && accountId !== 'unassigned' ? accountId : undefined)
      setImportMsg(`Imported ${r.inserted} of ${r.parsed} transactions (${r.duplicates_skipped} duplicates skipped).`)
      setPendingFile(null)
      setNeedsPassword(false)
      setPassword('')
      await load()
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Import failed'
      if (isPasswordError(msg)) {
        setPendingFile(file)
        setNeedsPassword(true)
        setImportMsg(cleanPasswordMessage(msg))
      } else {
        setNeedsPassword(false)
        setImportMsg(isKeyError(msg) ? cleanKeyMessage(msg) : msg)
      }
    } finally {
      setImporting(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setPassword('')
    setNeedsPassword(false)
    runImport(file)
  }

  function startNew() {
    const today = new Date().toISOString().slice(0, 10)
    setForm({ date: today.startsWith(month) ? today : `${month}-01`, description: '', amount: '', kind: 'debit', category: '', account_id: accountId && accountId !== 'unassigned' ? accountId : '' })
    setEditing('new')
  }

  function startEdit(t: Transaction) {
    setForm({
      date: t.transaction_date, description: t.description, amount: String(Math.abs(t.amount)),
      kind: t.amount < 0 ? 'debit' : 'credit', category: t.category ?? '', account_id: t.account_id ?? '',
    })
    setEditing(t.id)
  }

  async function onSubmitForm(e: React.FormEvent) {
    e.preventDefault()
    const magnitude = Math.abs(Number(form.amount))
    const body: Record<string, unknown> = {
      transaction_date: form.date,
      description: form.description.trim(),
      amount: form.kind === 'debit' ? -magnitude : magnitude,
    }
    if (form.category) body.category = form.category
    if (form.account_id) body.account_id = form.account_id
    setSaving(true)
    try {
      if (editing === 'new') await createTransaction(body)
      else if (editing) await updateTransaction(editing, body)
      setEditing(null)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setSaving(false)
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
            <select
              value={accountId} onChange={(e) => setAccountId(e.target.value)} aria-label="Account"
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">All accounts</option>
              {accounts.map((a) => <option key={a.id} value={a.id}>{a.bank_name} ····{a.last4}</option>)}
              <option value="unassigned">Unassigned</option>
            </select>
            <input ref={fileRef} type="file" accept=".csv,.pdf,image/*" onChange={onFile} className="hidden" />
            <button
              onClick={startNew}
              className="rounded-lg border border-slate-300 bg-white text-sm font-medium px-4 py-2 hover:border-indigo-300"
            >
              Add transaction
            </button>
            <button
              onClick={() => fileRef.current?.click()}
              disabled={importing}
              className="rounded-lg bg-indigo-600 text-white text-sm font-medium px-4 py-2 hover:bg-indigo-700 disabled:opacity-50"
            >
              {importing ? 'Importing…' : 'Import statement'}
            </button>
          </div>
        </div>

        <AIKeyBanner />

        {importing && (
          <p className="text-sm text-slate-600 bg-white border border-slate-200 rounded-lg px-4 py-2 flex items-center gap-2">
            <span className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
            Reading your statement… PDFs can take up to a minute. CSV files are instant.
          </p>
        )}
        {!importing && importMsg && <p className="text-sm text-slate-600 bg-white border border-slate-200 rounded-lg px-4 py-2">{importMsg}</p>}
        {needsPassword && pendingFile && !importing && (
          <form
            onSubmit={(e) => { e.preventDefault(); if (password) runImport(pendingFile, password) }}
            className="flex flex-wrap items-center gap-3 bg-white border border-slate-200 rounded-lg px-4 py-3"
          >
            <label className="text-sm text-slate-600" htmlFor="pdfpw">PDF password for {pendingFile.name}</label>
            <input
              id="pdfpw" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              autoComplete="off" className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
            />
            <button type="submit" disabled={!password} className="rounded-lg bg-indigo-600 text-white text-sm font-medium px-4 py-1.5 hover:bg-indigo-700 disabled:opacity-50">
              Unlock and import
            </button>
            <p className="w-full text-xs text-slate-400">The password is only used to open the file for this import and is never stored.</p>
          </form>
        )}
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

        {editing && (
          <form onSubmit={onSubmitForm} className="bg-white rounded-2xl border border-indigo-200 p-6 space-y-4">
            <h2 className="text-sm font-semibold text-slate-900">{editing === 'new' ? 'Add a transaction' : 'Edit transaction'}</h2>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 items-end">
              <label className="text-xs text-slate-600 space-y-1">
                <span>Date</span>
                <input type="date" required value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
              </label>
              <label className="text-xs text-slate-600 space-y-1 md:col-span-2">
                <span>Description</span>
                <input required value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
              </label>
              <label className="text-xs text-slate-600 space-y-1">
                <span>Type</span>
                <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">
                  <option value="debit">Money out</option>
                  <option value="credit">Money in</option>
                </select>
              </label>
              <label className="text-xs text-slate-600 space-y-1">
                <span>Amount (₹)</span>
                <input type="number" step="0.01" min="0.01" required value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
              </label>
              <label className="text-xs text-slate-600 space-y-1">
                <span>Account</span>
                <select value={form.account_id} onChange={(e) => setForm({ ...form, account_id: e.target.value })}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">
                  <option value="">{editing === 'new' ? 'Not linked' : 'Keep current'}</option>
                  {accounts.map((a) => <option key={a.id} value={a.id}>{a.bank_name} ····{a.last4}</option>)}
                </select>
              </label>
              <label className="text-xs text-slate-600 space-y-1">
                <span>Category</span>
                <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">
                  <option value="">{editing === 'new' ? 'Auto-detect' : 'Keep current'}</option>
                  {categories.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>
            </div>
            <div className="flex gap-2">
              <button type="submit" disabled={saving} className="rounded-lg bg-indigo-600 text-white text-sm font-medium px-4 py-2 hover:bg-indigo-700 disabled:opacity-50">
                {saving ? 'Saving…' : 'Save'}
              </button>
              <button type="button" onClick={() => setEditing(null)} className="rounded-lg border border-slate-300 text-sm px-4 py-2 text-slate-600">Cancel</button>
            </div>
          </form>
        )}

        <SpendTrendChart refreshKey={refreshKey} accountId={accountId || undefined} />
        <RecurringPayments refreshKey={refreshKey} accountId={accountId || undefined} />

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
                      <td className="py-2 pr-4 text-slate-800 max-w-xs">
                        <p className="truncate">{t.description}</p>
                        {t.account_last4 && <p className="text-[11px] text-slate-400">{t.bank_name} ····{t.account_last4}</p>}
                      </td>
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
                      <td className="py-2 text-right whitespace-nowrap">
                        <button onClick={() => startEdit(t)} className="text-xs text-indigo-600 hover:text-indigo-800 mr-3">Edit</button>
                        <button onClick={() => onDelete(t.id)} className="text-xs text-red-500 hover:text-red-700">Delete</button>
                      </td>
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
