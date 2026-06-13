'use client'

import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer, type TooltipProps } from 'recharts'
import { formatINR, compactINR } from '@/lib/format'

interface Breakdown {
  investments: number
  epf_nps: number
  bank_balance: number
}

interface Props {
  breakdown: Breakdown
}

const SLICES = [
  { key: 'investments' as const, label: 'Investments', color: '#6366f1' },
  { key: 'epf_nps'     as const, label: 'EPF / NPS',   color: '#14b8a6' },
  { key: 'bank_balance'as const, label: 'Bank',         color: '#3b82f6' },
]

function CustomTooltip({ active, payload }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null
  const { name, value } = payload[0]
  return (
    <div className="bg-white border border-slate-200 rounded-lg shadow-sm px-3 py-2">
      <p className="text-xs text-slate-500 mb-0.5">{name}</p>
      <p className="text-sm font-semibold text-slate-800">{formatINR(value ?? 0)}</p>
    </div>
  )
}

function renderLegend(total: number) {
  return function LegendContent({ payload }: { payload?: Array<{ color: string; value: string; payload: { value: number } }> }) {
    if (!payload) return null
    return (
      <ul className="space-y-2 mt-2">
        {payload.map((entry) => {
          const pct = total > 0 ? ((entry.payload.value / total) * 100).toFixed(1) : '0.0'
          return (
            <li key={entry.value} className="flex items-center justify-between text-xs">
              <span className="flex items-center gap-1.5 text-slate-600">
                <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: entry.color }} />
                {entry.value}
              </span>
              <span className="font-medium text-slate-700 tabular-nums">
                {compactINR(entry.payload.value)}{' '}
                <span className="text-slate-400">({pct}%)</span>
              </span>
            </li>
          )
        })}
      </ul>
    )
  }
}

export default function AssetBreakdownChart({ breakdown }: Props) {
  const data = SLICES
    .map(({ key, label, color }) => ({ name: label, value: breakdown[key], color }))
    .filter((d) => d.value > 0)

  const total = data.reduce((sum, d) => sum + d.value, 0)

  if (data.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-sm text-slate-400">
        No assets recorded yet.
      </div>
    )
  }

  const LegendContent = renderLegend(total)

  return (
    <div className="space-y-2">
      <ResponsiveContainer width="100%" height={180}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={55}
            outerRadius={80}
            paddingAngle={3}
            dataKey="value"
            startAngle={90}
            endAngle={-270}
          >
            {data.map((entry) => (
              <Cell key={entry.name} fill={entry.color} stroke="none" />
            ))}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
        </PieChart>
      </ResponsiveContainer>
      <Legend content={<LegendContent payload={data.map(d => ({ color: d.color, value: d.name, payload: { value: d.value } }))} />} />
    </div>
  )
}
