'use client'

import { useCallback, useEffect, useState } from 'react'

import FileImporter from '@/components/dashboard/FileImporter'
import {
  deleteLoanStatement, getLoanAccount, importLoanStatement, updateItem,
  type Loan, type LoanAccount as Account, type LoanTxnKind,
} from '@/lib/api'
import { formatINR } from '@/lib/format'

const fmtDate = (iso: string) => new Date(iso + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })

const KINDS: Record<LoanTxnKind, { label: string; tone: string }> = {
  disbursement: { label: 'Disbursed', tone: 'bg-indigo-50 text-indigo-700' },
  emi: { label: 'EMI', tone: 'bg-emerald-50 text-emerald-700' },
  prepayment: { label: 'Prepayment', tone: 'bg-emerald-50 text-emerald-700' },
  interest: { label: 'Interest', tone: 'bg-amber-50 text-amber-800' },
  principal: { label: 'Principal', tone: 'bg-emerald-50 text-emerald-700' },
  charge: { label: 'Charge', tone: 'bg-red-50 text-red-700' },
  other: { label: 'Other', tone: 'bg-slate-100 text-slate-600' },
}
const PAGE = 50

export default function LoanAccount({ loan, onChange }: { loan: Loan; onChange: () => void }) {
  const [data, setData] = useState<Account | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<LoanTxnKind | 'all'>('all')
  const [shown, setShown] = useState(PAGE)
  const [showStatements, setShowStatements] = useState(false)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try { setData(await getLoanAccount(loan.id)); setError(null) } catch (e) { setError(e instanceof Error ? e.message : 'Failed to load') }
  }, [loan.id])
  useEffect(() => { load() }, [load])

  async function applyBalance(balance: number) {
    setBusy(true)
    try { await updateItem('loans', loan.id, { outstanding_amount: balance }); onChange() } catch (e) { setError(e instanceof Error ? e.message : 'Could not update') } finally { setBusy(false) }
  }
  async function removeStatement(id: string) {
    if (!confirm('Remove this statement and the transactions imported from it?')) return
    try { await deleteLoanStatement(id); await load() } catch (e) { setError(e instanceof Error ? e.message : 'Could not remove') }
  }

  const s = data?.summary
  const txns = (data?.transactions ?? []).filter((t) => filter === 'all' || t.kind === filter)
  const kindsPresent = Array.from(new Set((data?.transactions ?? []).map((t) => t.kind)))

  return (
    <div className="space-y-4 border-t border-slate-100 pt-5">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">Loan statement</h3>
          <p className="text-xs text-slate-500 mt-0.5">Upload the lender&apos;s statement (PDF, image or CSV) to see what you have actually paid.</p>
        </div>
        <FileImporter
          label="Import loan statement"
          accept=".pdf,.csv,image/*"
          onDone={() => { setShown(PAGE); load() }}
          onImport={async (file, pw) => {
            const r = await importLoanStatement(loan.id, file, pw)
            return `Imported statement of ${fmtDate(r.statement.statement_date)}: ${r.transactions_inserted} transactions${r.duplicates_skipped ? ` (${r.duplicates_skipped} already existed)` : ''}.`
          }}
        />
      </div>

      {error && <p className="text-xs text-red-500">{error}</p>}

      {s && s.transaction_count === 0 && <p className="text-sm text-slate-400">No statement imported yet.</p>}

      {s && s.transaction_count > 0 && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            {[
              ['Interest paid so far', formatINR(s.interest_paid)],
              ['Principal paid so far', formatINR(s.principal_paid)],
              ['Balance (principal)', s.balance != null ? formatINR(s.balance) : 'Not in statement'],
              ['Total paid', formatINR(s.total_paid)],
              ['Charges & fees', formatINR(s.charges_paid)],
            ].map(([label, value]) => (
              <div key={label} className="rounded-xl bg-slate-50 border border-slate-200 p-4">
                <p className="text-[11px] text-slate-500 uppercase tracking-wide">{label}</p>
                <p className="text-base font-semibold text-slate-900 mt-1">{value}</p>
              </div>
            ))}
          </div>
          <p className="text-xs text-slate-500">
            {s.transaction_count} transactions from {fmtDate(s.first_date!)} to {fmtDate(s.last_date!)}
            {s.balance_as_of ? ` · balance as of ${fmtDate(s.balance_as_of)}` : ''}
            {s.prepaid > 0 ? ` · includes ${formatINR(s.prepaid)} prepaid` : ''}.
          </p>

          {s.unsplit_emis > 0 && (
            <p className="text-xs text-amber-700">
              {s.unsplit_emis} EMI{s.unsplit_emis === 1 ? '' : 's'} could not be split into principal and interest because the statement has no balance
              for them, so the totals above leave {s.unsplit_emis === 1 ? 'it' : 'them'} out. Importing the statement from the start of the loan fixes this.
            </p>
          )}
          {s.balance != null && Math.abs(s.balance - loan.outstanding_amount) > 1 && (
            <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-3 flex items-center justify-between gap-3 flex-wrap">
              <p className="text-xs text-indigo-900">
                The statement shows {formatINR(s.balance)} outstanding, but this loan is set to {formatINR(loan.outstanding_amount)}. Net worth uses the loan&apos;s amount.
              </p>
              <button onClick={() => applyBalance(s.balance!)} disabled={busy} className="rounded-lg bg-indigo-600 text-white text-xs font-medium px-3 py-1.5 hover:bg-indigo-700 disabled:opacity-50">
                {busy ? 'Updating…' : `Set outstanding to ${formatINR(s.balance)}`}
              </button>
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            {(['all', ...kindsPresent] as const).map((k) => (
              <button
                key={k}
                onClick={() => { setFilter(k); setShown(PAGE) }}
                className={`px-3 py-1 rounded-full text-xs border transition-colors ${filter === k ? 'bg-indigo-600 border-indigo-600 text-white' : 'border-slate-200 text-slate-600 hover:border-slate-300'}`}
              >
                {k === 'all' ? 'All' : KINDS[k].label}
              </button>
            ))}
          </div>

          <div className="overflow-x-auto rounded-lg border border-slate-200">
            <table className="w-full text-xs">
              <thead className="bg-slate-50">
                <tr className="text-left text-slate-500">
                  <th className="py-2 px-3 font-medium">Date</th><th className="font-medium">Description</th><th className="font-medium">Type</th>
                  <th className="font-medium text-right">Amount</th><th className="font-medium text-right">Principal</th>
                  <th className="font-medium text-right">Interest</th><th className="font-medium text-right px-3">Balance</th>
                </tr>
              </thead>
              <tbody>
                {txns.slice(0, shown).map((t) => (
                  <tr key={t.id} className="border-t border-slate-100 text-slate-800">
                    <td className="py-1.5 px-3 whitespace-nowrap">{fmtDate(t.txn_date)}</td>
                    <td className="pr-3 max-w-xs truncate" title={t.description}>{t.description}</td>
                    <td><span className={`px-2 py-0.5 rounded-full ${KINDS[t.kind].tone}`}>{KINDS[t.kind].label}</span></td>
                    <td className="text-right">{formatINR(t.amount)}</td>
                    <td className="text-right">{t.principal_amount != null ? formatINR(t.principal_amount) : '–'}</td>
                    <td className="text-right">{t.interest_amount != null ? formatINR(t.interest_amount) : '–'}</td>
                    <td className="text-right px-3">{t.balance_after != null ? formatINR(t.balance_after) : '–'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {txns.length > shown && (
            <button onClick={() => setShown(shown + PAGE)} className="text-sm text-indigo-600 hover:text-indigo-800">Show more ({txns.length - shown} left)</button>
          )}

          <div>
            <button onClick={() => setShowStatements(!showStatements)} className="text-sm text-slate-500 hover:text-slate-800">
              {showStatements ? 'Hide imported statements' : `Imported statements (${data!.statements.length})`}
            </button>
            {showStatements && (
              <ul className="divide-y divide-slate-100 mt-2">
                {data!.statements.map((st) => (
                  <li key={st.id} className="py-2 flex items-center justify-between gap-3 text-sm">
                    <span className="text-slate-700">
                      {st.period_start && st.period_end ? `${fmtDate(st.period_start)} – ${fmtDate(st.period_end)}` : `Statement of ${fmtDate(st.statement_date)}`}
                      {st.closing_balance != null && <span className="text-slate-400"> · closing {formatINR(st.closing_balance)}</span>}
                    </span>
                    <button onClick={() => removeStatement(st.id)} className="text-xs text-red-500 hover:text-red-700">Remove</button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  )
}
