'use client'

import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { getSpendTrend, type SpendTrend } from '@/lib/api'
import { compactINR, formatINR } from '@/lib/format'

const PALETTE = ['#6366f1', '#f59e0b', '#10b981', '#ef4444', '#06b6d4', '#94a3b8']
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const label = (ym: string) => `${MONTHS[Number(ym.slice(5, 7)) - 1]} ${ym.slice(2, 4)}`

export default function SpendTrendChart({ refreshKey, accountId }: { refreshKey?: number; accountId?: string }) {
  const [trend, setTrend] = useState<SpendTrend | null>(null)
  const [months, setMonths] = useState(6)
  const [view, setView] = useState<'flow' | 'categories'>('flow')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getSpendTrend(months, accountId).then((t) => { setTrend(t); setError(null) }).catch((e) => setError(e instanceof Error ? e.message : 'Failed to load trend'))
  }, [months, refreshKey, accountId])

  const data = trend?.months.map((m) => ({ ...m, ...m.categories, label: label(m.month) })) ?? []
  const empty = trend && trend.months.every((m) => m.income === 0 && m.expenses === 0)

  return (
    <section className="bg-white rounded-2xl border border-slate-200 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Spend trend</h2>
          {trend && trend.average_monthly_spend > 0 && (
            <p className="text-xs text-slate-500 mt-0.5">Average spend {formatINR(trend.average_monthly_spend)} per month</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {(['flow', 'categories'] as const).map((v) => (
            <button key={v} onClick={() => setView(v)}
              className={`px-3 py-1 rounded-md text-xs font-medium ${view === v ? 'bg-indigo-600 text-white' : 'bg-white border border-slate-200 text-slate-600'}`}>
              {v === 'flow' ? 'Income vs spend' : 'By category'}
            </button>
          ))}
          <select value={months} onChange={(e) => setMonths(Number(e.target.value))} className="rounded-md border border-slate-200 text-xs px-2 py-1">
            {[3, 6, 12].map((n) => <option key={n} value={n}>{n} months</option>)}
          </select>
        </div>
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}
      {!error && !trend && <p className="text-sm text-slate-400">Loading…</p>}
      {empty && <p className="text-sm text-slate-400">No transactions in this period yet.</p>}

      {trend && !empty && (
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
              <XAxis dataKey="label" tick={{ fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis tickFormatter={(v: number) => compactINR(v)} tick={{ fontSize: 12 }} axisLine={false} tickLine={false} width={56} />
              <Tooltip formatter={(v: number) => formatINR(v)} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {view === 'flow' ? (
                <>
                  <Bar dataKey="income" name="Income" fill="#10b981" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="expenses" name="Spend" fill="#ef4444" radius={[3, 3, 0, 0]} />
                </>
              ) : (
                trend.top_categories.map((c, i) => (
                  <Bar key={c} dataKey={c} stackId="cat" fill={PALETTE[i % PALETTE.length]} />
                ))
              )}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  )
}
