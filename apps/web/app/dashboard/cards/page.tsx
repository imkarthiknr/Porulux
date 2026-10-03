'use client'

import { useCallback, useEffect, useState } from 'react'

import DashboardNav from '@/components/dashboard/DashboardNav'
import FileImporter from '@/components/dashboard/FileImporter'
import {
  createCreditCard, deleteCardStatement, deleteCreditCard, getCardsOverview, getStatementTransactions, importCardStatement,
  listCardStatements, updateCardStatement, updateCreditCard,
  type CardDue, type CardOverviewItem, type CardStatement, type CardsOverview, type CreditCard,
} from '@/lib/api'
import { formatINR } from '@/lib/format'

const NETWORKS = ['VISA', 'MASTERCARD', 'AMEX', 'RUPAY', 'DINERS', 'OTHER'] as const
const BANKS = ['HDFC Bank', 'ICICI Bank', 'State Bank of India (SBI Card)', 'Axis Bank', 'American Express', 'Kotak Mahindra Bank', 'IDFC FIRST Bank', 'Yes Bank', 'IndusInd Bank', 'Standard Chartered', 'HSBC', 'RBL Bank', 'AU Small Finance Bank']
const input = 'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500'
const fmtDate = (iso: string) => new Date(iso + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })

function dueText(d: CardDue) {
  if (d.overdue) return `Overdue by ${Math.abs(d.days_left)} day${Math.abs(d.days_left) === 1 ? '' : 's'}`
  if (d.days_left === 0) return 'Due today'
  return `Due in ${d.days_left} day${d.days_left === 1 ? '' : 's'}`
}
const dueTone = (d: CardDue) => (d.overdue ? 'bg-red-50 border-red-200 text-red-800' : d.days_left <= 5 ? 'bg-amber-50 border-amber-200 text-amber-900' : 'bg-slate-50 border-slate-200 text-slate-700')

interface FormState { bank_name: string; card_name: string; network: string; last4: string; credit_limit: string; statement_day: string; due_day: string; annual_fee: string; interest_rate: string }
const blank: FormState = { bank_name: '', card_name: '', network: '', last4: '', credit_limit: '', statement_day: '', due_day: '', annual_fee: '', interest_rate: '' }
const toForm = (c: CreditCard): FormState => ({
  bank_name: c.bank_name, card_name: c.card_name ?? '', network: c.network ?? '', last4: c.last4,
  credit_limit: c.credit_limit != null ? String(c.credit_limit) : '', statement_day: c.statement_day != null ? String(c.statement_day) : '',
  due_day: c.due_day != null ? String(c.due_day) : '', annual_fee: c.annual_fee != null ? String(c.annual_fee) : '', interest_rate: c.interest_rate != null ? String(c.interest_rate) : '',
})

function CardForm({ initial, editingId, onSaved, onCancel }: { initial: FormState; editingId?: string; onSaved: () => void; onCancel: () => void }) {
  const [f, setF] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const num = (k: keyof FormState) => (f[k] === '' ? (editingId ? null : undefined) : Number(f[k]))

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    const body: Record<string, unknown> = {
      bank_name: f.bank_name.trim(), card_name: f.card_name.trim() || (editingId ? null : undefined), last4: f.last4,
      network: f.network || (editingId ? null : undefined), credit_limit: num('credit_limit'), statement_day: num('statement_day'),
      due_day: num('due_day'), annual_fee: num('annual_fee'), interest_rate: num('interest_rate'),
    }
    Object.keys(body).forEach((k) => body[k] === undefined && delete body[k])
    setBusy(true)
    setError(null)
    try {
      if (editingId) await updateCreditCard(editingId, body)
      else await createCreditCard(body)
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save')
    } finally {
      setBusy(false)
    }
  }

  const field = (k: keyof FormState, label: string, extra: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <label className="text-xs text-slate-600 space-y-1">
      <span>{label}</span>
      <input className={input} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} {...extra} />
    </label>
  )

  return (
    <form onSubmit={onSubmit} className="bg-white rounded-2xl border border-indigo-200 p-6 space-y-4">
      <h2 className="text-sm font-semibold text-slate-900">{editingId ? 'Edit card' : 'Add a credit card'}</h2>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <label className="text-xs text-slate-600 space-y-1">
          <span>Issuing bank</span>
          <input className={input} list="card-banks" required value={f.bank_name} onChange={(e) => setF({ ...f, bank_name: e.target.value })} />
          <datalist id="card-banks">{BANKS.map((b) => <option key={b} value={b} />)}</datalist>
        </label>
        {field('card_name', 'Card name (e.g. Regalia)')}
        <label className="text-xs text-slate-600 space-y-1">
          <span>Network</span>
          <select className={input} value={f.network} onChange={(e) => setF({ ...f, network: e.target.value })}>
            <option value="">—</option>
            {NETWORKS.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        {field('last4', 'Last 4 digits', { required: true, inputMode: 'numeric', maxLength: 4, pattern: '[0-9]{4}', onChange: (e) => setF({ ...f, last4: e.target.value.replace(/\D/g, '') }) })}
        {field('credit_limit', 'Credit limit (₹)', { type: 'number', min: 0, step: 'any' })}
        {field('annual_fee', 'Annual fee (₹)', { type: 'number', min: 0, step: 'any' })}
        {field('statement_day', 'Statement day of month', { type: 'number', min: 1, max: 31 })}
        {field('due_day', 'Payment due day of month', { type: 'number', min: 1, max: 31 })}
        {field('interest_rate', 'Interest rate (% p.a.)', { type: 'number', min: 0, step: 'any' })}
      </div>
      <p className="text-xs text-slate-400">Only the last 4 digits are stored. Never enter the full card number, expiry or CVV.</p>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={busy} className="rounded-lg bg-indigo-600 text-white text-sm font-medium px-4 py-2 hover:bg-indigo-700 disabled:opacity-50">{busy ? 'Saving…' : 'Save card'}</button>
        <button type="button" onClick={onCancel} className="rounded-lg border border-slate-300 text-sm px-4 py-2 text-slate-600">Cancel</button>
      </div>
    </form>
  )
}

function StatementRow({ s, onChange }: { s: CardStatement; onChange: () => void }) {
  const [open, setOpen] = useState(false)
  const [detail, setDetail] = useState<Awaited<ReturnType<typeof getStatementTransactions>> | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function toggle() {
    const next = !open
    setOpen(next)
    if (next && !detail) {
      try { setDetail(await getStatementTransactions(s.id)) } catch (e) { setError(e instanceof Error ? e.message : 'Failed to load') }
    }
  }
  async function setPaid(paid: boolean) {
    try { await updateCardStatement(s.id, { paid }); onChange() } catch (e) { setError(e instanceof Error ? e.message : 'Failed to update') }
  }
  async function remove() {
    if (!window.confirm('Delete this statement and its transactions?')) return
    try { await deleteCardStatement(s.id); onChange() } catch (e) { setError(e instanceof Error ? e.message : 'Failed to delete') }
  }

  const maxCat = Math.max(1, ...(detail?.by_category.map((c) => c.total) ?? [1]))
  return (
    <li className="py-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-medium text-slate-800">{fmtDate(s.statement_date)}</p>
          <p className="text-xs text-slate-500">
            {s.period_start && s.period_end ? `${fmtDate(s.period_start)} – ${fmtDate(s.period_end)} · ` : ''}
            {s.due_date ? `due ${fmtDate(s.due_date)}` : 'no due date (CSV)'}
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <p className="font-semibold text-slate-900">{formatINR(s.total_due)}</p>
            {s.minimum_due != null && <p className="text-xs text-slate-500">min {formatINR(s.minimum_due)}</p>}
          </div>
          <label className="flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer">
            <input type="checkbox" checked={s.paid} onChange={(e) => setPaid(e.target.checked)} /> Paid
          </label>
          <button onClick={toggle} className="text-xs text-indigo-600 hover:text-indigo-800">{open ? 'Hide' : 'Details'}</button>
          <button onClick={remove} className="text-xs text-red-500 hover:text-red-700">Delete</button>
        </div>
      </div>
      {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
      {open && detail && (
        <div className="mt-3 grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div>
            <p className="text-xs font-medium text-slate-500 mb-2">Spend by category</p>
            {detail.by_category.length === 0 ? <p className="text-xs text-slate-400">No spends.</p> : (
              <ul className="space-y-1.5">
                {detail.by_category.map((c) => (
                  <li key={c.category} className="text-xs">
                    <div className="flex justify-between"><span>{c.category}</span><span>{formatINR(c.total)}</span></div>
                    <div className="h-1.5 bg-slate-100 rounded-full mt-0.5"><div className="h-1.5 bg-indigo-500 rounded-full" style={{ width: `${(c.total / maxCat) * 100}%` }} /></div>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="lg:col-span-2 max-h-72 overflow-auto rounded-lg border border-slate-200">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-slate-50"><tr className="text-left text-slate-500"><th className="py-1.5 px-3 font-medium">Date</th><th className="font-medium">Description</th><th className="font-medium">Category</th><th className="font-medium text-right px-3">Amount</th></tr></thead>
              <tbody>
                {detail.transactions.map((t) => (
                  <tr key={t.id} className="border-t border-slate-100">
                    <td className="py-1.5 px-3 whitespace-nowrap">{t.txn_date}</td>
                    <td className="max-w-[16rem] truncate">{t.description}</td>
                    <td>{t.category}</td>
                    <td className={`text-right px-3 whitespace-nowrap ${t.amount < 0 ? 'text-green-600' : 'text-slate-800'}`}>{t.amount < 0 ? '-' : ''}{formatINR(t.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </li>
  )
}

function CardPanel({ item, onChange, onEdit }: { item: CardOverviewItem; onChange: () => void; onEdit: () => void }) {
  const { card } = item
  const [statements, setStatements] = useState<CardStatement[] | null>(null)
  const [showStatements, setShowStatements] = useState(false)

  const loadStatements = useCallback(async () => {
    try { setStatements(await listCardStatements(card.id)) } catch { setStatements([]) }
  }, [card.id])
  useEffect(() => { if (showStatements) loadStatements() }, [showStatements, loadStatements, item.last_statement?.id, item.statement_count])

  async function onDelete() {
    if (!window.confirm(`Remove ${card.bank_name} ····${card.last4} and all its statements?`)) return
    try { await deleteCreditCard(card.id); onChange() } catch { /* shown by reload */ }
  }

  const util = item.utilization_pct
  const bar = util == null ? 'bg-slate-300' : util > 75 ? 'bg-red-500' : util > 30 ? 'bg-amber-500' : 'bg-emerald-500'
  return (
    <section className="bg-white rounded-2xl border border-slate-200 p-6 space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-base font-semibold text-slate-900">
            {card.bank_name}{card.card_name ? ` ${card.card_name}` : ''} <span className="text-slate-400 font-normal">····{card.last4}</span>
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            {[card.network, card.statement_day ? `statement on ${card.statement_day}th` : null, card.due_day ? `due on ${card.due_day}th` : null, card.annual_fee ? `annual fee ${formatINR(card.annual_fee)}` : null, card.interest_rate ? `${card.interest_rate}% p.a.` : null].filter(Boolean).join(' · ')}
          </p>
        </div>
        {item.next_due && (
          <div className={`rounded-lg border px-3 py-2 text-xs ${dueTone(item.next_due)}`}>
            <p className="font-semibold">{dueText(item.next_due)}{item.next_due.estimated ? ' (estimated)' : ''}</p>
            <p>{fmtDate(item.next_due.date)}{item.next_due.amount_due > 0 ? ` · ${formatINR(item.next_due.amount_due)}` : ''}{item.next_due.minimum_due ? ` · min ${formatINR(item.next_due.minimum_due)}` : ''}</p>
          </div>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3 text-sm">
        <div><p className="text-[11px] text-slate-500 uppercase tracking-wide">Outstanding</p><p className="font-semibold text-slate-900">{formatINR(item.outstanding)}</p></div>
        <div><p className="text-[11px] text-slate-500 uppercase tracking-wide">Limit</p><p className="font-semibold text-slate-900">{item.credit_limit != null ? formatINR(item.credit_limit) : '—'}</p></div>
        <div><p className="text-[11px] text-slate-500 uppercase tracking-wide">Available</p><p className="font-semibold text-slate-900">{item.available_credit != null ? formatINR(item.available_credit) : '—'}</p></div>
      </div>
      {util != null && (
        <div>
          <div className="h-2 bg-slate-100 rounded-full"><div className={`h-2 rounded-full ${bar}`} style={{ width: `${Math.min(util, 100)}%` }} /></div>
          <p className="text-xs text-slate-500 mt-1">{util}% of limit used{util > 30 ? ' (keeping it under 30% helps your credit score)' : ''}</p>
        </div>
      )}

      <FileImporter
        label="Import statement"
        accept=".pdf,.csv,image/*"
        onDone={() => { onChange(); if (showStatements) loadStatements() }}
        onImport={async (file, pw) => {
          const r = await importCardStatement(card.id, file, pw)
          return `Imported statement of ${fmtDate(r.statement.statement_date)}: ${r.transactions_inserted} transactions${r.duplicates_skipped ? ` (${r.duplicates_skipped} already existed)` : ''}.`
        }}
      />

      <div className="flex gap-4 text-sm pt-1 border-t border-slate-100">
        <button onClick={() => setShowStatements(!showStatements)} className="text-indigo-600 hover:text-indigo-800">
          {showStatements ? 'Hide statements' : `Statements (${item.statement_count})`}
        </button>
        <button onClick={onEdit} className="text-slate-500 hover:text-slate-800">Edit card</button>
        <button onClick={onDelete} className="text-red-500 hover:text-red-700">Remove</button>
      </div>

      {showStatements && (
        statements === null ? <p className="text-sm text-slate-400">Loading…</p>
          : statements.length === 0 ? <p className="text-sm text-slate-400">No statements yet. Import one above.</p>
            : <ul className="divide-y divide-slate-100">{statements.map((s) => <StatementRow key={s.id} s={s} onChange={() => { onChange(); loadStatements() }} />)}</ul>
      )}
    </section>
  )
}

export default function CardsPage() {
  const [data, setData] = useState<CardsOverview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState<{ id?: string; state: FormState } | null>(null)

  const load = useCallback(async () => {
    try { setData(await getCardsOverview()); setError(null) } catch (e) { setError(e instanceof Error ? e.message : 'Failed to load') }
  }, [])
  useEffect(() => { load() }, [load])

  return (
    <div className="min-h-screen bg-slate-50">
      <DashboardNav active="/dashboard/cards" />
      <main className="max-w-6xl mx-auto px-6 py-8 space-y-6">
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">Credit cards</h1>
            <p className="text-sm text-slate-500 mt-0.5">Limits, utilisation, statements and due dates. Unpaid statements count as liabilities in your net worth.</p>
          </div>
          <button onClick={() => setForm({ state: blank })} className="rounded-lg bg-indigo-600 text-white text-sm font-medium px-4 py-2 hover:bg-indigo-700">Add card</button>
        </div>

        {error && <p className="text-sm text-red-500">{error}</p>}
        {form && <CardForm key={form.id ?? 'new'} initial={form.state} editingId={form.id} onCancel={() => setForm(null)} onSaved={() => { setForm(null); load() }} />}
        {!data && !error && <p className="text-sm text-slate-400">Loading…</p>}

        {data && data.upcoming_dues.length > 0 && (
          <div className="space-y-2">
            {data.upcoming_dues.map((d) => (
              <div key={d.card_id} className={`rounded-xl border px-4 py-3 text-sm flex flex-wrap justify-between gap-2 ${dueTone(d)}`}>
                <span><strong>{d.label}</strong> · {dueText(d)} ({fmtDate(d.date)})</span>
                <span>{formatINR(d.amount_due)}{d.minimum_due ? ` · min ${formatINR(d.minimum_due)}` : ''}</span>
              </div>
            ))}
          </div>
        )}

        {data && data.cards.length > 0 && (
          <div className="grid grid-cols-3 gap-4">
            {[['Total limit', formatINR(data.totals.credit_limit)], ['Outstanding', formatINR(data.totals.outstanding)], ['Utilisation', data.totals.utilization_pct != null ? `${data.totals.utilization_pct}%` : '—']].map(([l, v]) => (
              <div key={l} className="bg-white rounded-2xl border border-slate-200 p-5">
                <p className="text-xs text-slate-500 uppercase tracking-wide">{l}</p>
                <p className="text-xl font-semibold text-slate-900 mt-1">{v}</p>
              </div>
            ))}
          </div>
        )}

        {data && data.cards.length === 0 && !form && (
          <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center">
            <p className="text-sm text-slate-500">No credit cards yet.</p>
            <p className="text-xs text-slate-400 mt-1">Add a card, then import its monthly statement (PDF or CSV).</p>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {data?.cards.map((item) => (
            <CardPanel key={item.card.id} item={item} onChange={load} onEdit={() => setForm({ id: item.card.id, state: toForm(item.card) })} />
          ))}
        </div>
      </main>
    </div>
  )
}
