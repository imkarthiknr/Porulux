'use client'

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'

import DashboardNav from '@/components/dashboard/DashboardNav'
import FileImporter from '@/components/dashboard/FileImporter'
import {
  assignUnassigned, createBankAccount, deleteBankAccount, getBankSummary, importStatement, updateBankAccount,
  type BankAccountSummary, type BankSummary,
} from '@/lib/api'
import { formatINR } from '@/lib/format'

const BANKS = ['HDFC Bank', 'ICICI Bank', 'State Bank of India', 'Axis Bank', 'Kotak Mahindra Bank', 'IDFC FIRST Bank', 'Yes Bank', 'IndusInd Bank', 'Punjab National Bank', 'Bank of Baroda', 'Canara Bank', 'Federal Bank', 'Union Bank of India']
const TYPES = [['SAVINGS', 'Savings'], ['SALARY', 'Salary'], ['CURRENT', 'Current']] as const
const input = 'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500'
const signed = (n: number) => `${n < 0 ? '-' : ''}${formatINR(n)}`

interface FormState { bank_name: string; account_type: string; last4: string; nickname: string; ifsc: string }
const blank: FormState = { bank_name: '', account_type: 'SAVINGS', last4: '', nickname: '', ifsc: '' }

function AccountForm({ initial, onSaved, onCancel, editingId }: { initial: FormState; editingId?: string; onSaved: () => void; onCancel: () => void }) {
  const [f, setF] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    const body: Record<string, unknown> = { bank_name: f.bank_name.trim(), account_type: f.account_type, last4: f.last4, nickname: f.nickname.trim() || null }
    // ifsc: only send when filled (the API validates the format), clear it on edit when emptied
    if (f.ifsc.trim()) body.ifsc = f.ifsc.trim().toUpperCase()
    else if (editingId) body.ifsc = null
    setBusy(true)
    setError(null)
    try {
      if (editingId) await updateBankAccount(editingId, body)
      else await createBankAccount(body)
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={onSubmit} className="bg-white rounded-2xl border border-indigo-200 p-6 space-y-4">
      <h2 className="text-sm font-semibold text-slate-900">{editingId ? 'Edit account' : 'Add a bank account'}</h2>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <label className="text-xs text-slate-600 space-y-1">
          <span>Bank name</span>
          <input className={input} list="banks" required value={f.bank_name} onChange={(e) => setF({ ...f, bank_name: e.target.value })} />
          <datalist id="banks">{BANKS.map((b) => <option key={b} value={b} />)}</datalist>
        </label>
        <label className="text-xs text-slate-600 space-y-1">
          <span>Account type</span>
          <select className={input} value={f.account_type} onChange={(e) => setF({ ...f, account_type: e.target.value })}>
            {TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        <label className="text-xs text-slate-600 space-y-1">
          <span>Last 4 digits of account number</span>
          <input className={input} required inputMode="numeric" pattern="[0-9]{4}" maxLength={4} value={f.last4} onChange={(e) => setF({ ...f, last4: e.target.value.replace(/\D/g, '') })} />
        </label>
        <label className="text-xs text-slate-600 space-y-1">
          <span>Nickname (optional)</span>
          <input className={input} value={f.nickname} onChange={(e) => setF({ ...f, nickname: e.target.value })} placeholder="Salary account" />
        </label>
        <label className="text-xs text-slate-600 space-y-1">
          <span>IFSC (optional)</span>
          <input className={input} value={f.ifsc} onChange={(e) => setF({ ...f, ifsc: e.target.value })} placeholder="HDFC0001234" maxLength={11} />
        </label>
      </div>
      <p className="text-xs text-slate-400">Only the last 4 digits are stored. Never enter a full account number.</p>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={busy} className="rounded-lg bg-indigo-600 text-white text-sm font-medium px-4 py-2 hover:bg-indigo-700 disabled:opacity-50">{busy ? 'Saving…' : 'Save account'}</button>
        <button type="button" onClick={onCancel} className="rounded-lg border border-slate-300 text-sm px-4 py-2 text-slate-600">Cancel</button>
      </div>
    </form>
  )
}

export default function BanksPage() {
  const [data, setData] = useState<BankSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState<{ id?: string; state: FormState } | null>(null)
  const [assignTo, setAssignTo] = useState('')
  const [notice, setNotice] = useState<string | null>(null)

  const load = useCallback(async () => {
    try { setData(await getBankSummary()); setError(null) } catch (e) { setError(e instanceof Error ? e.message : 'Failed to load') }
  }, [])
  useEffect(() => { load() }, [load])

  function edit(a: BankAccountSummary) {
    setForm({ id: a.id, state: { bank_name: a.bank_name, account_type: a.account_type, last4: a.last4, nickname: a.nickname ?? '', ifsc: a.ifsc ?? '' } })
  }

  async function onDelete(a: BankAccountSummary) {
    if (!window.confirm(`Remove ${a.bank_name} ····${a.last4}? Its ${a.transaction_count} transactions are kept but become unassigned.`)) return
    try { await deleteBankAccount(a.id); await load() } catch (e) { setError(e instanceof Error ? e.message : 'Failed to delete') }
  }

  async function onAssign() {
    if (!assignTo) return
    try {
      const r = await assignUnassigned(assignTo)
      setNotice(`Moved ${r.assigned} transactions to that account.`)
      setAssignTo('')
      await load()
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to assign') }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <DashboardNav active="/dashboard/banks" />
      <main className="max-w-6xl mx-auto px-6 py-8 space-y-6">
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">Bank accounts</h1>
            <p className="text-sm text-slate-500 mt-0.5">Add each savings account, then import its statements so every transaction lands on the right account.</p>
          </div>
          <button onClick={() => setForm({ state: blank })} className="rounded-lg bg-indigo-600 text-white text-sm font-medium px-4 py-2 hover:bg-indigo-700">Add account</button>
        </div>

        {error && <p className="text-sm text-red-500">{error}</p>}
        {notice && <p className="text-sm text-green-600">{notice}</p>}
        {form && <AccountForm key={form.id ?? 'new'} initial={form.state} editingId={form.id} onCancel={() => setForm(null)} onSaved={() => { setForm(null); load() }} />}

        {!data && !error && <p className="text-sm text-slate-400">Loading…</p>}

        {data && data.unassigned.count > 0 && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 flex flex-wrap items-center gap-3">
            <span>{data.unassigned.count} transactions ({signed(data.unassigned.balance)}) are not linked to any account.</span>
            {data.accounts.length > 0 && (
              <span className="flex items-center gap-2">
                <select value={assignTo} onChange={(e) => setAssignTo(e.target.value)} className="rounded-lg border border-amber-300 bg-white px-2 py-1 text-sm">
                  <option value="">Move them to…</option>
                  {data.accounts.map((a) => <option key={a.id} value={a.id}>{a.bank_name} ····{a.last4}</option>)}
                </select>
                <button onClick={onAssign} disabled={!assignTo} className="rounded-lg bg-amber-600 text-white text-sm font-medium px-3 py-1 disabled:opacity-50">Move</button>
              </span>
            )}
          </div>
        )}

        {data && data.accounts.length === 0 && !form && (
          <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center">
            <p className="text-sm text-slate-500">No bank accounts yet.</p>
            <p className="text-xs text-slate-400 mt-1">Add one, then import its statement from here.</p>
          </div>
        )}

        {data && data.accounts.length > 0 && (
          <>
            <div className="bg-white rounded-2xl border border-slate-200 px-6 py-4 flex items-center justify-between">
              <span className="text-sm text-slate-500">Total across accounts</span>
              <span className="text-xl font-semibold text-slate-900">{signed(data.total_balance)}</span>
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {data.accounts.map((a) => (
                <section key={a.id} className="bg-white rounded-2xl border border-slate-200 p-6 space-y-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h2 className="text-base font-semibold text-slate-900 truncate">{a.bank_name} <span className="text-slate-400 font-normal">····{a.last4}</span></h2>
                      <p className="text-xs text-slate-500 mt-0.5">
                        {TYPES.find(([v]) => v === a.account_type)?.[1]}{a.nickname ? ` · ${a.nickname}` : ''}{a.ifsc ? ` · ${a.ifsc}` : ''}
                      </p>
                    </div>
                    <div className="text-right shrink-0">
                      <p className={`text-lg font-semibold ${a.balance < 0 ? 'text-red-600' : 'text-slate-900'}`}>{signed(a.balance)}</p>
                      <p className="text-xs text-slate-400">{a.transaction_count} txns{a.last_transaction_date ? ` · to ${a.last_transaction_date}` : ''}</p>
                    </div>
                  </div>
                  <FileImporter
                    label={`Import ${a.bank_name} statement`}
                    onDone={load}
                    onImport={async (file, pw) => {
                      const r = await importStatement(file, undefined, pw, a.id)
                      return `Imported ${r.inserted} of ${r.parsed} transactions${r.duplicates_skipped ? ` (${r.duplicates_skipped} already existed)` : ''}.`
                    }}
                  />
                  <div className="flex gap-4 text-sm pt-1 border-t border-slate-100">
                    <Link href={`/dashboard/transactions?account=${a.id}`} className="text-indigo-600 hover:text-indigo-800">View transactions</Link>
                    <button onClick={() => edit(a)} className="text-slate-500 hover:text-slate-800">Edit</button>
                    <button onClick={() => onDelete(a)} className="text-red-500 hover:text-red-700">Remove</button>
                  </div>
                </section>
              ))}
            </div>
          </>
        )}
      </main>
    </div>
  )
}
