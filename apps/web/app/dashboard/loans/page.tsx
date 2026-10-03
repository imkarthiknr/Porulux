'use client'

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'

import DashboardNav from '@/components/dashboard/DashboardNav'
import { getLoanTracker, listItems, updateItem, type Loan, type LoanTracker } from '@/lib/api'
import { formatINR } from '@/lib/format'

const LABELS: Record<string, string> = {
  HOME_LOAN: 'Home loan', PERSONAL_LOAN: 'Personal loan', VEHICLE_LOAN: 'Vehicle loan', CREDIT_CARD: 'Credit card', OTHER: 'Other',
}
const input = 'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500'

function DetailsForm({ loan, onSaved, onCancel }: { loan: Loan; onSaved: () => void; onCancel?: () => void }) {
  const [f, setF] = useState({
    principal_amount: loan.principal_amount != null ? String(loan.principal_amount) : '',
    interest_rate: loan.interest_rate != null ? String(loan.interest_rate) : '',
    tenure_months: loan.tenure_months != null ? String(loan.tenure_months) : '',
    start_date: loan.start_date ?? '',
    emi_amount: loan.emi_amount != null ? String(loan.emi_amount) : '',
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    const body: Record<string, unknown> = {}
    if (f.principal_amount) body.principal_amount = Number(f.principal_amount)
    if (f.interest_rate) body.interest_rate = Number(f.interest_rate)
    if (f.tenure_months) body.tenure_months = Number(f.tenure_months)
    if (f.start_date) body.start_date = f.start_date
    if (f.emi_amount) body.emi_amount = Number(f.emi_amount)
    setBusy(true)
    try { await updateItem('loans', loan.id, body); onSaved() } catch (err) { setError(err instanceof Error ? err.message : 'Failed to save') } finally { setBusy(false) }
  }

  const fields: [keyof typeof f, string, string, string?][] = [
    ['principal_amount', 'Original loan amount (₹)', 'number'],
    ['interest_rate', 'Interest rate (% p.a.)', 'number'],
    ['tenure_months', 'Tenure (months)', 'number'],
    ['start_date', 'Loan start / disbursal date', 'date'],
    ['emi_amount', 'EMI (₹), optional if amount is given', 'number'],
  ]
  return (
    <form onSubmit={onSubmit} className="space-y-3">
      <p className="text-xs text-slate-500">These let Porulux rebuild your EMI schedule and work out interest paid and tax benefit.</p>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {fields.map(([name, label, type]) => (
          <label key={name} className="text-xs text-slate-600 space-y-1">
            <span>{label}</span>
            <input className={input} type={type} step={type === 'number' ? 'any' : undefined} value={f[name]} onChange={(e) => setF({ ...f, [name]: e.target.value })} />
          </label>
        ))}
      </div>
      {error && <p className="text-xs text-red-500">{error}</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={busy} className="rounded-lg bg-indigo-600 text-white text-sm font-medium px-4 py-2 hover:bg-indigo-700 disabled:opacity-50">{busy ? 'Saving…' : 'Save details'}</button>
        {onCancel && <button type="button" onClick={onCancel} className="rounded-lg border border-slate-300 text-sm px-4 py-2 text-slate-600">Cancel</button>}
      </div>
    </form>
  )
}

function Tracker({ loan, onChange }: { loan: Loan; onChange: () => void }) {
  const [t, setT] = useState<LoanTracker | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [showSchedule, setShowSchedule] = useState(false)

  const load = useCallback(async () => {
    try { setT(await getLoanTracker(loan.id)); setError(null) } catch (e) { setT(null); setError(e instanceof Error ? e.message : 'Failed to load') }
  }, [loan.id, loan.interest_rate, loan.tenure_months, loan.start_date, loan.principal_amount, loan.emi_amount])
  useEffect(() => { load() }, [load])

  if (error) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-amber-700">{error}</p>
        <DetailsForm loan={loan} onSaved={() => { onChange(); load() }} />
      </div>
    )
  }
  if (!t) return <p className="text-sm text-slate-400">Loading…</p>

  const s = t.summary
  const entered = t.loan.outstanding_amount
  const drift = Math.abs(entered - s.outstanding_principal)
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        {[
          ['Outstanding (schedule)', formatINR(s.outstanding_principal)],
          ['EMI', formatINR(s.emi)],
          ['Interest paid so far', formatINR(s.interest_paid_to_date)],
          ['Principal repaid', formatINR(s.principal_paid_to_date)],
          ['EMIs left', `${s.emis_remaining} · ends ${s.payoff_date?.slice(0, 7)}`],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl bg-slate-50 border border-slate-200 p-4">
            <p className="text-[11px] text-slate-500 uppercase tracking-wide">{label}</p>
            <p className="text-base font-semibold text-slate-900 mt-1">{value}</p>
          </div>
        ))}
      </div>
      {drift > Math.max(5000, entered * 0.02) && (
        <p className="text-xs text-amber-700">
          You entered {formatINR(entered)} outstanding but the schedule says {formatINR(s.outstanding_principal)}. Part-payments, rate changes or a
          different start date cause this. Net worth uses the amount you entered; update it in Accounts if needed.
        </p>
      )}

      {t.tax_applicable ? (
        <div>
          <h3 className="text-sm font-semibold text-slate-900 mb-2">Tax benefit by financial year (old regime)</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-500 border-b border-slate-100">
                  <th className="py-2 pr-4 font-medium">FY</th>
                  <th className="py-2 pr-4 font-medium text-right">Interest paid</th>
                  <th className="py-2 pr-4 font-medium text-right">24(b) deduction</th>
                  <th className="py-2 pr-4 font-medium text-right">Principal repaid</th>
                  <th className="py-2 pr-4 font-medium text-right">80C (principal)</th>
                </tr>
              </thead>
              <tbody>
                {s.tax_by_year.map((y) => (
                  <tr key={y.financial_year} className={`border-b border-slate-50 ${y.financial_year === s.current_financial_year ? 'bg-indigo-50/50' : ''}`}>
                    <td className="py-2 pr-4 whitespace-nowrap">{y.financial_year}{y.financial_year === s.current_financial_year ? ' (current)' : ''}</td>
                    <td className="py-2 pr-4 text-right">{formatINR(y.interest)}</td>
                    <td className="py-2 pr-4 text-right font-medium">{formatINR(y.deduction_24b)}</td>
                    <td className="py-2 pr-4 text-right">{formatINR(y.principal)}</td>
                    <td className="py-2 pr-4 text-right font-medium">{formatINR(y.deduction_80c_principal)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-slate-400 mt-2">
            24(b) is capped at ₹2,00,000 for a self-occupied home. 80C principal counts toward the shared ₹1,50,000 limit with PF, ELSS, life insurance
            and similar, so your real 80C room is smaller. Both apply only under the old tax regime. Figures are estimates from the schedule, so check the
            lender’s annual interest certificate when filing.
          </p>
        </div>
      ) : (
        <p className="text-xs text-slate-500">Tax deductions tracked for home loans only.</p>
      )}

      <div className="flex gap-4">
        <button onClick={() => setShowSchedule(!showSchedule)} className="text-sm text-indigo-600 hover:text-indigo-800">
          {showSchedule ? 'Hide EMI schedule' : `Show EMI schedule (${t.schedule.length} instalments)`}
        </button>
        <button onClick={() => setEditing(!editing)} className="text-sm text-slate-500 hover:text-slate-800">Edit loan details</button>
      </div>
      {editing && <DetailsForm loan={loan} onSaved={() => { setEditing(false); onChange() }} onCancel={() => setEditing(false)} />}

      {showSchedule && (
        <div className="max-h-96 overflow-auto rounded-lg border border-slate-200">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-slate-50">
              <tr className="text-left text-slate-500">
                <th className="py-2 px-3 font-medium">#</th><th className="font-medium">Due</th>
                <th className="font-medium text-right">Interest</th><th className="font-medium text-right">Principal</th>
                <th className="font-medium text-right">EMI</th><th className="font-medium text-right px-3">Balance</th>
              </tr>
            </thead>
            <tbody>
              {t.schedule.map((r) => (
                <tr key={r.number} className={`border-t border-slate-100 ${r.paid ? 'text-slate-400' : 'text-slate-800'}`}>
                  <td className="py-1.5 px-3">{r.number}</td><td>{r.due_date}</td>
                  <td className="text-right">{formatINR(r.interest)}</td><td className="text-right">{formatINR(r.principal)}</td>
                  <td className="text-right">{formatINR(r.emi)}</td><td className="text-right px-3">{formatINR(r.closing)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default function LoansPage() {
  const [loans, setLoans] = useState<Loan[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try { setLoans(await listItems<Loan>('loans')); setError(null) } catch (e) { setError(e instanceof Error ? e.message : 'Failed to load') } finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])

  return (
    <div className="min-h-screen bg-slate-50">
      <DashboardNav active="/dashboard/loans" />
      <main className="max-w-6xl mx-auto px-6 py-8 space-y-6">
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">Loans</h1>
            <p className="text-sm text-slate-500 mt-0.5">EMI schedule, interest paid to date, and home loan tax benefit (80C and 24(b)).</p>
          </div>
          <Link href="/dashboard/accounts" className="rounded-lg border border-slate-300 bg-white text-sm font-medium px-4 py-2 hover:border-indigo-300">Add a loan</Link>
        </div>

        {error && <p className="text-sm text-red-500">{error}</p>}
        {loading && <p className="text-sm text-slate-400">Loading…</p>}
        {!loading && loans.length === 0 && (
          <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center">
            <p className="text-sm text-slate-500">No loans yet. Add one under Accounts.</p>
          </div>
        )}

        {loans.map((loan) => (
          <section key={loan.id} className="bg-white rounded-2xl border border-slate-200 p-6 space-y-4">
            <div className="flex items-baseline justify-between gap-3 flex-wrap">
              <h2 className="text-base font-semibold text-slate-900">
                {LABELS[loan.loan_type] ?? loan.loan_type}{loan.lender_name ? ` · ${loan.lender_name}` : ''}
              </h2>
              <p className="text-sm text-slate-500">Outstanding entered: <strong className="text-slate-900">{formatINR(loan.outstanding_amount)}</strong></p>
            </div>
            <Tracker loan={loan} onChange={load} />
          </section>
        ))}
      </main>
    </div>
  )
}
