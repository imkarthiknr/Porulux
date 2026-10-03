'use client'

import Link from 'next/link'
import { Fragment, useCallback, useEffect, useState } from 'react'

import DashboardNav from '@/components/dashboard/DashboardNav'
import HoldingsImporter from '@/components/dashboard/HoldingsImporter'
import {
  addLot, deleteLot, getInvestmentReturns, listLots,
  type HoldingReturn, type InvestmentReturns, type Lot,
} from '@/lib/api'
import { formatINR } from '@/lib/format'

const ago = (iso?: string | null) => {
  if (!iso) return null
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000))
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  if (mins < 1440) return `${Math.round(mins / 60)} h ago`
  return `${Math.round(mins / 1440)} d ago`
}
const PRICE_DOT: Record<string, { cls: string; tip: string }> = {
  live: { cls: 'bg-emerald-500', tip: 'Live price' },
  cached: { cls: 'bg-emerald-300', tip: 'Recent price (refreshed in the last few minutes)' },
  stale: { cls: 'bg-amber-500', tip: 'Could not fetch a new price. Showing the last known one.' },
  manual: { cls: 'bg-slate-300', tip: 'No automatic price for this type. Update it by hand under Accounts.' },
}
const pct = (n: number | null | undefined) => (n == null ? '—' : `${n > 0 ? '+' : ''}${n.toFixed(2)}%`)
const tone = (n: number | null | undefined) => (n == null ? 'text-slate-500' : n >= 0 ? 'text-green-600' : 'text-red-600')

function Lots({ holding, onChange }: { holding: HoldingReturn; onChange: () => void }) {
  const [lots, setLots] = useState<Lot[]>([])
  const [form, setForm] = useState({ lot_date: '', lot_type: 'BUY' as 'BUY' | 'SELL', units: '', price: '' })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try { setLots(await listLots(holding.holding_id)) } catch (e) { setError(e instanceof Error ? e.message : 'Failed to load lots') }
  }, [holding.holding_id])
  useEffect(() => { load() }, [load])

  async function onAdd(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await addLot(holding.holding_id, { lot_date: form.lot_date, lot_type: form.lot_type, units: Number(form.units), price: Number(form.price) })
      setForm({ ...form, units: '', price: '' })
      await load()
      onChange()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add lot')
    } finally {
      setBusy(false)
    }
  }

  async function onDelete(id: string) {
    try { await deleteLot(id); await load(); onChange() } catch (err) { setError(err instanceof Error ? err.message : 'Failed to delete') }
  }

  const input = 'rounded-lg border border-slate-300 px-3 py-1.5 text-sm'
  return (
    <div className="bg-slate-50 rounded-xl p-4 space-y-3">
      <p className="text-xs text-slate-500">
        Add each purchase (and sale) with its date. XIRR is calculated from these dated cash flows plus today’s value.
      </p>
      {lots.length > 0 && (
        <table className="w-full text-xs">
          <thead><tr className="text-left text-slate-500"><th className="py-1">Date</th><th>Type</th><th className="text-right">Units</th><th className="text-right">Price</th><th /></tr></thead>
          <tbody>
            {lots.map((l) => (
              <tr key={l.id} className="border-t border-slate-200">
                <td className="py-1">{l.lot_date}{l.assumed && <span className="ml-1 text-[10px] text-amber-600">approx.</span>}</td><td>{l.lot_type}</td>
                <td className="text-right">{l.units}</td><td className="text-right">{formatINR(l.price)}</td>
                <td className="text-right"><button onClick={() => onDelete(l.id)} className="text-red-500 hover:text-red-700">Delete</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <form onSubmit={onAdd} className="flex flex-wrap gap-2 items-end">
        <input type="date" required className={input} value={form.lot_date} onChange={(e) => setForm({ ...form, lot_date: e.target.value })} aria-label="Date" />
        <select className={input} value={form.lot_type} onChange={(e) => setForm({ ...form, lot_type: e.target.value as 'BUY' | 'SELL' })} aria-label="Type">
          <option value="BUY">Buy</option><option value="SELL">Sell</option>
        </select>
        <input type="number" step="any" min="0.000001" required placeholder="Units" className={`${input} w-28`} value={form.units} onChange={(e) => setForm({ ...form, units: e.target.value })} />
        <input type="number" step="any" min="0" required placeholder="Price (₹)" className={`${input} w-32`} value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} />
        <button type="submit" disabled={busy} className="rounded-lg bg-indigo-600 text-white text-sm font-medium px-4 py-1.5 hover:bg-indigo-700 disabled:opacity-50">Add lot</button>
      </form>
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  )
}

export default function InvestmentsPage() {
  const [data, setData] = useState<InvestmentReturns | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)

  const [refreshing, setRefreshing] = useState(false)

  // Show stored prices straight away, then replace them with live ones. Gains and XIRR are recomputed
  // by the API from whatever price it holds, so they move as soon as the live prices land.
  const load = useCallback(async (mode: 'auto' | 'force' = 'auto') => {
    setError(null)
    try {
      if (mode === 'auto') setData(await getInvestmentReturns('off'))
      setRefreshing(true)
      setData(await getInvestmentReturns(mode))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setRefreshing(false)
    }
  }, [])
  useEffect(() => { load() }, [load])

  const p = data?.portfolio
  return (
    <div className="min-h-screen bg-slate-50">
      <DashboardNav active="/dashboard/investments" />
      <main className="max-w-6xl mx-auto px-6 py-8 space-y-6">
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">Investments</h1>
            <p className="text-sm text-slate-500 mt-0.5">Returns per holding and for the whole portfolio, including XIRR.</p>
          </div>
          <Link href="/dashboard/accounts" className="rounded-lg border border-slate-300 bg-white text-sm font-medium px-4 py-2 hover:border-indigo-300">
            Add or edit holdings
          </Link>
        </div>

        {error && <p className="text-sm text-red-500">{error}</p>}
        {!data && !error && <p className="text-sm text-slate-400">Loading…</p>}
        {data && <HoldingsImporter onImported={() => load()} startOpen={data.holdings.length === 0} />}

        {data && data.holdings.length === 0 && (
          <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center">
            <p className="text-sm text-slate-500">No holdings yet.</p>
            <p className="text-xs text-slate-400 mt-1">Import a broker statement above, or add holdings one by one under Accounts. Then record buy dates here for XIRR.</p>
          </div>
        )}

        {p && data!.holdings.length > 0 && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
              <span>
                {refreshing ? 'Updating prices…' : data!.prices?.updated_at ? `Prices updated ${ago(data!.prices.updated_at)}` : 'Prices not refreshed yet'}
                {!refreshing && data!.prices && data!.prices.stale > 0 && (
                  <span className="text-amber-600"> · {data!.prices.stale} holding{data!.prices.stale === 1 ? '' : 's'} could not be priced</span>
                )}
              </span>
              <button onClick={() => load('force')} disabled={refreshing} className="text-indigo-600 hover:text-indigo-800 disabled:opacity-50">
                Refresh prices
              </button>
            </div>
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
              {[
                ['Invested', formatINR(p.invested), ''],
                ['Current value', formatINR(p.current_value), ''],
                ['Gain / loss', `${p.gain < 0 ? '-' : ''}${formatINR(p.gain)}`, tone(p.gain)],
                ['Absolute return', pct(p.absolute_return_pct), tone(p.absolute_return_pct)],
                [p.xirr_approx ? 'XIRR (approx.)' : 'XIRR', `${p.xirr_approx && p.xirr_pct != null ? '~' : ''}${pct(p.xirr_pct)}`, tone(p.xirr_pct)],
              ].map(([label, value, cls]) => (
                <div key={label} className="bg-white rounded-2xl border border-slate-200 p-5">
                  <p className="text-xs text-slate-500 uppercase tracking-wide">{label}</p>
                  <p className={`text-xl font-semibold mt-1 ${cls || 'text-slate-900'}`}>{value}</p>
                </div>
              ))}
            </div>
            {p.xirr_pct == null && (
              <p className="text-xs text-slate-500">XIRR needs buy dates. Expand a holding and add when you bought it, or import again with “Held since”.</p>
            )}

            <section className="bg-white rounded-2xl border border-slate-200 p-6 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-500 border-b border-slate-100">
                    <th className="py-2 pr-4 font-medium">Holding</th>
                    <th className="py-2 pr-4 font-medium text-right">Invested</th>
                    <th className="py-2 pr-4 font-medium text-right">Value</th>
                    <th className="py-2 pr-4 font-medium text-right">Return</th>
                    <th className="py-2 pr-4 font-medium text-right">XIRR</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {data!.holdings.map((h) => (
                    <Fragment key={h.holding_id}>
                      <tr className="border-b border-slate-50">
                        <td className="py-2 pr-4">
                          <p className="font-medium text-slate-800">{h.name}</p>
                          <p className="text-xs text-slate-500 flex items-center gap-1.5">
                            {h.price_status && (
                              <span title={`${PRICE_DOT[h.price_status].tip}${h.price_source ? ` (${h.price_source})` : ''}`}
                                className={`inline-block w-2 h-2 rounded-full ${PRICE_DOT[h.price_status].cls}`} />
                            )}
                            <span>{h.symbol} · {h.holding_type} · {h.units} units · {h.lots} lots{h.source ? ` · ${h.source}` : ''}</span>
                          </p>
                        </td>
                        <td className="py-2 pr-4 text-right">{h.invested == null ? '—' : formatINR(h.invested)}</td>
                        <td className="py-2 pr-4 text-right">{h.current_value == null ? '—' : formatINR(h.current_value)}</td>
                        <td className={`py-2 pr-4 text-right ${tone(h.absolute_return_pct)}`}>{pct(h.absolute_return_pct)}</td>
                        <td className={`py-2 pr-4 text-right ${tone(h.xirr_pct)}`} title={h.xirr_approx ? 'Estimated from your “held since” date, not real purchase dates' : undefined}>{h.xirr_approx && h.xirr_pct != null ? '~' : ''}{pct(h.xirr_pct)}</td>
                        <td className="py-2 text-right">
                          <button onClick={() => setOpen(open === h.holding_id ? null : h.holding_id)} className="text-xs text-indigo-600 hover:text-indigo-800">
                            {open === h.holding_id ? 'Hide lots' : 'Lots'}
                          </button>
                        </td>
                      </tr>
                      {open === h.holding_id && (
                        <tr><td colSpan={6} className="pb-3"><Lots holding={h} onChange={() => load()} /></td></tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </section>
          </>
        )}
      </main>
    </div>
  )
}
