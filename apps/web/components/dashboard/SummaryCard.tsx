import { formatINR, formatINRSigned } from '@/lib/format'

type Variant = 'asset' | 'liability' | 'networth' | 'change'

interface Props {
  label: string
  value: number
  variant?: Variant
  changePct?: number
}

const valueStyles: Record<Variant, string> = {
  asset:      'text-slate-900',
  liability:  'text-red-600',
  networth:   'text-indigo-600',
  change:     '', // set dynamically
}

export default function SummaryCard({ label, value, variant = 'asset', changePct }: Props) {
  const isChange = variant === 'change'
  const isNegative = value < 0

  const dynamicColor = isChange
    ? isNegative ? 'text-red-600' : 'text-emerald-600'
    : valueStyles[variant]

  const displayValue = isChange ? formatINRSigned(value) : formatINR(value)

  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-1">
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">{label}</p>
      <p className={`text-2xl font-semibold tabular-nums ${dynamicColor}`}>
        {displayValue}
      </p>
      {isChange && changePct !== undefined && (
        <p className={`text-xs font-medium ${isNegative ? 'text-red-500' : 'text-emerald-500'}`}>
          {isNegative ? '▼' : '▲'} {Math.abs(changePct).toFixed(1)}% vs prev snapshot
        </p>
      )}
    </div>
  )
}
