'use client'

import { useEffect, useState } from 'react'

import { getRecurring, type RecurringItem } from '@/lib/api'
import { formatINR } from '@/lib/format'

const fmt = (iso: string) => new Date(iso + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })

export default function RecurringPayments({ refreshKey }: { refreshKey?: number }) {
  const [data, setData] = useState<{ items: RecurringItem[]; monthly_commitments: number } | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getRecurring().then((d) => { setData(d); setError(null) }).catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
  }, [refreshKey])

  const expenses = data?.items.filter((i) => i.direction === 'expense') ?? []
  const income = data?.items.filter((i) => i.direction === 'income') ?? []

  return (
    <section className="bg-white rounded-2xl border border-slate-200 p-6">
      <div className="flex items-end justify-between gap-3 mb-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Recurring payments</h2>
          <p className="text-xs text-slate-500 mt-0.5">Detected from your last 12 months: same payee, steady interval, 3+ times.</p>
        </div>
        {data && data.monthly_commitments > 0 && (
          <p className="text-right text-xs text-slate-500">
            Monthly commitments<br />
            <span className="text-base font-semibold text-slate-900">{formatINR(data.monthly_commitments)}</span>
          </p>
        )}
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}
      {!error && !data && <p className="text-sm text-slate-400">Loading…</p>}
      {data && data.items.length === 0 && (
        <p className="text-sm text-slate-400">Nothing recurring found yet. Import a few months of statements for better detection.</p>
      )}

      {expenses.length > 0 && (
        <ul className="divide-y divide-slate-100">
          {expenses.map((r) => (
            <li key={r.name} className="py-2.5 flex items-center justify-between gap-3 text-sm">
              <div className="min-w-0">
                <p className="font-medium text-slate-800 truncate">{r.name}</p>
                <p className="text-xs text-slate-500">
                  {r.frequency}{r.variable ? ' · varies' : ''} · {r.occurrences}× · next ≈ {fmt(r.next_expected)}
                </p>
              </div>
              <span className="text-slate-900 whitespace-nowrap">
                {r.variable ? '≈ ' : ''}{formatINR(r.typical_amount)}
              </span>
            </li>
          ))}
        </ul>
      )}

      {income.length > 0 && (
        <div className="mt-4 pt-4 border-t border-slate-100">
          <p className="text-xs font-medium text-slate-500 mb-1">Regular income</p>
          <ul>
            {income.map((r) => (
              <li key={r.name} className="py-1.5 flex justify-between text-sm">
                <span className="text-slate-700">{r.name} <span className="text-xs text-slate-400">· {r.frequency}</span></span>
                <span className="text-green-600">{formatINR(r.typical_amount)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
