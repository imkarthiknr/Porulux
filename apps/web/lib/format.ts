const inrFormatter = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
})

// Full Indian format: ₹12,34,567
export function formatINR(amount: number): string {
  return inrFormatter.format(Math.abs(amount))
}

// Compact for chart axes and secondary labels: ₹12.3L, ₹1.2Cr
export function compactINR(value: number): string {
  const abs = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  if (abs >= 1_00_00_000) return `${sign}₹${(abs / 1_00_00_000).toFixed(1)}Cr`
  if (abs >= 1_00_000) return `${sign}₹${(abs / 1_00_000).toFixed(1)}L`
  if (abs >= 1_000) return `${sign}₹${(abs / 1_000).toFixed(1)}K`
  return `${sign}₹${abs}`
}

// Signed version for deltas: +₹12,345 or -₹12,345
export function formatINRSigned(amount: number): string {
  const prefix = amount >= 0 ? '+' : '-'
  return `${prefix}${formatINR(amount)}`
}
