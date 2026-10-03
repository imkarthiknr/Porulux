'use client'

import Link from 'next/link'
import { useRef, useState } from 'react'

import {
  cleanKeyMessage, cleanPasswordMessage, confirmHoldingsImport, isKeyError, isPasswordError, previewHoldingsImport,
  type HoldingKind, type ImportEntry, type ImportPreview,
} from '@/lib/api'
import { formatINR } from '@/lib/format'

const SOURCES = ['Zerodha', 'Groww', 'Upstox', 'Angel One', 'ICICI Direct', 'HDFC Securities', 'Kotak Securities', 'Paytm Money', '5paisa', 'CAMS', 'KFintech', 'NSDL CAS', 'CDSL CAS']
const KINDS: HoldingKind[] = ['STOCK', 'MF', 'ETF', 'BOND', 'SGB', 'OTHER']
const BADGE = {
  new: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  update: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  unchanged: 'bg-slate-50 text-slate-500 border-slate-200',
} as const
const field = (k: string) => k.replace('_', ' ')
const num = (n: number | null) => (n == null ? '—' : n.toLocaleString('en-IN', { maximumFractionDigits: 4 }))

type Row = ImportEntry & { include: boolean }

export default function HoldingsImporter({ onImported, startOpen }: { onImported: () => void; startOpen: boolean }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [open, setOpen] = useState(startOpen)
  const [source, setSource] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [password, setPassword] = useState('')
  const [needsPassword, setNeedsPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [keyProblem, setKeyProblem] = useState(false)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [rows, setRows] = useState<Row[]>([])
  const [removeMissing, setRemoveMissing] = useState(false)
  const [heldSince, setHeldSince] = useState('')
  const [done, setDone] = useState<string | null>(null)

  function reset() {
    setFile(null); setPassword(''); setNeedsPassword(false); setError(null); setKeyProblem(false)
    setPreview(null); setRows([]); setRemoveMissing(false); setHeldSince('')
    if (fileRef.current) fileRef.current.value = ''
  }

  async function run(f: File, pw?: string) {
    setBusy(true); setError(null); setKeyProblem(false); setDone(null)
    try {
      const p = await previewHoldingsImport(f, source.trim() || undefined, pw)
      setPreview(p)
      setRows(p.entries.map((e) => ({ ...e, include: e.action !== 'unchanged' })))
      setSource(p.source)
      setNeedsPassword(false)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Could not read the statement'
      setPreview(null)
      if (isPasswordError(msg)) { setNeedsPassword(true); setError(cleanPasswordMessage(msg)) }
      else if (isKeyError(msg)) { setKeyProblem(true); setError(cleanKeyMessage(msg)) }
      else { setNeedsPassword(false); setError(msg) }
    } finally {
      setBusy(false)
    }
  }

  function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (!f) return
    setFile(f); setPassword(''); setNeedsPassword(false)
    run(f)
  }

  async function onConfirm() {
    if (!preview) return
    const chosen = rows.filter((r) => r.include)
    setBusy(true); setError(null)
    try {
      const r = await confirmHoldingsImport({
        source: source.trim() || preview.source,
        rows: chosen.map((x) => ({
          name: x.name, symbol: x.symbol, isin: x.isin, holding_type: x.holding_type, units: x.units,
          avg_buy_price: x.avg_buy_price, current_price: x.current_price, existing_id: x.existing_id,
        })),
        remove_ids: removeMissing ? preview.missing.map((m) => m.id) : [],
        assumed_buy_date: heldSince || undefined,
      })
      setDone(`Done: ${r.inserted} added, ${r.updated} updated${r.removed ? `, ${r.removed} removed` : ''}. ${r.assumed_lots ? `XIRR is an estimate based on your “held since” date. Add real buy dates under “Lots” to sharpen it.` : 'Add buy dates under “Lots” on any holding, or import again with “Held since”, to get XIRR.'}`)
      reset()
      onImported()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the import')
    } finally {
      setBusy(false)
    }
  }

  const selected = rows.filter((r) => r.include)
  const input = 'rounded-lg border border-slate-300 px-3 py-1.5 text-sm'

  return (
    <section className="bg-white rounded-2xl border border-indigo-200">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center justify-between gap-3 px-6 py-4 text-left">
        <span>
          <span className="block text-sm font-semibold text-slate-900">Import holdings from a statement</span>
          <span className="block text-xs text-slate-500 mt-0.5">
            Upload your broker holdings (CSV, Excel) or a CAS / statement PDF. Repeat for each broker you use.
          </span>
        </span>
        <span className="text-xs text-indigo-600 shrink-0">{open ? 'Hide' : 'Open'}</span>
      </button>

      {open && (
        <div className="px-6 pb-6 space-y-4 border-t border-slate-100 pt-4">
          {done && <p className="text-sm text-green-600">{done}</p>}

          {!preview && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-end gap-3">
                <label className="text-xs text-slate-600 space-y-1">
                  <span>Broker / source (optional, detected when possible)</span>
                  <input className={`${input} block w-56`} list="broker-sources" value={source} onChange={(e) => setSource(e.target.value)} placeholder="e.g. Zerodha" />
                  <datalist id="broker-sources">{SOURCES.map((s) => <option key={s} value={s} />)}</datalist>
                </label>
                <input ref={fileRef} type="file" accept=".csv,.xlsx,.xlsm,.pdf,image/*" className="hidden" onChange={onPick} />
                <button onClick={() => fileRef.current?.click()} disabled={busy}
                  className="rounded-lg bg-indigo-600 text-white text-sm font-medium px-4 py-2 hover:bg-indigo-700 disabled:opacity-50">
                  {busy ? 'Reading statement…' : 'Choose file'}
                </button>
              </div>
              <p className="text-xs text-slate-400">
                Where to get it: Zerodha Console → Portfolio → Holdings → download. Groww → Profile → Reports → Holdings. Upstox, Angel One and ICICI Direct → Holdings → download.
                For mutual funds, a CAS PDF from CAMS or KFintech covers every fund house. PDFs need your AI key (Settings); CSV and Excel do not.
              </p>

              {busy && <p className="text-xs text-slate-500">PDFs can take up to a minute. CSV and Excel are instant.</p>}
              {needsPassword && file && !busy && (
                <form onSubmit={(e) => { e.preventDefault(); if (password) run(file, password) }} className="flex flex-wrap items-center gap-2">
                  <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="off" autoFocus
                    placeholder={`Password for ${file.name}`} aria-label="PDF password" className={input} />
                  <button type="submit" disabled={!password} className="rounded-lg bg-indigo-600 text-white text-sm font-medium px-3 py-1.5 disabled:opacity-50">Unlock</button>
                  <span className="text-xs text-slate-400">CAS passwords are usually your PAN (and date of birth). Used once, never stored.</span>
                </form>
              )}
              {error && !busy && (
                <p className={`text-sm ${needsPassword ? 'text-slate-600' : 'text-red-600'}`}>
                  {error} {keyProblem && <Link href="/dashboard/settings" className="underline font-medium">Open Settings</Link>}
                </p>
              )}
            </div>
          )}

          {preview && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-slate-900">
                    {rows.length} holdings found in <span className="text-indigo-700">{file?.name}</span>
                  </p>
                  <p className="text-xs text-slate-500">
                    {preview.counts.new} new · {preview.counts.update} to update · {preview.counts.unchanged} unchanged · value {formatINR(preview.totals.current_value)}
                  </p>
                </div>
                <label className="text-xs text-slate-600 flex items-center gap-2">
                  Source
                  <input className={`${input} w-44`} list="broker-sources" value={source} onChange={(e) => setSource(e.target.value)} />
                </label>
              </div>

              {preview.warnings.length > 0 && (
                <ul className="text-xs text-amber-700 list-disc pl-5">{preview.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
              )}

              <div className="overflow-x-auto rounded-lg border border-slate-200 max-h-96 overflow-y-auto">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-slate-50">
                    <tr className="text-left text-slate-500">
                      <th className="py-2 px-3 w-8">
                        <input type="checkbox" checked={rows.length > 0 && rows.every((r) => r.include)} aria-label="Select all"
                          onChange={(e) => setRows(rows.map((r) => ({ ...r, include: e.target.checked })))} />
                      </th>
                      <th className="font-medium">Holding</th><th className="font-medium">Type</th>
                      <th className="font-medium text-right">Units</th><th className="font-medium text-right">Avg cost</th>
                      <th className="font-medium text-right">Price</th><th className="font-medium text-right px-3">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r, i) => (
                      <tr key={r.key + i} className={`border-t border-slate-100 ${r.include ? '' : 'opacity-50'}`}>
                        <td className="py-2 px-3">
                          <input type="checkbox" checked={r.include} aria-label={`Include ${r.name}`}
                            onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, include: e.target.checked } : x)))} />
                        </td>
                        <td className="py-2 pr-3 max-w-[18rem]">
                          <p className="truncate text-slate-800" title={r.name}>{r.name}</p>
                          <p className="text-[11px] text-slate-400 flex items-center gap-1.5">
                            <span className={`border rounded px-1 ${BADGE[r.action]}`}>{r.action}</span>
                            {r.symbol !== r.name && <span>{r.symbol}</span>}{r.isin && <span>{r.isin}</span>}
                          </p>
                          {r.action === 'update' && Object.keys(r.changes).length > 0 && (
                            <p className="text-[11px] text-indigo-600">
                              {Object.entries(r.changes).map(([k, v]) => `${field(k)} ${num(v.from)} → ${num(v.to)}`).join(' · ')}
                            </p>
                          )}
                        </td>
                        <td>
                          <select value={r.holding_type} aria-label={`Type of ${r.name}`} className="rounded border border-slate-200 px-1 py-0.5 bg-white"
                            onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, holding_type: e.target.value as HoldingKind } : x)))}>
                            {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
                          </select>
                        </td>
                        <td className="text-right">{num(r.units)}</td>
                        <td className="text-right">{num(r.avg_buy_price)}</td>
                        <td className="text-right">{num(r.current_price)}</td>
                        <td className="text-right px-3">{r.current_value != null ? formatINR(r.current_value) : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {preview.missing.length > 0 && (
                <label className="flex items-start gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-900 cursor-pointer">
                  <input type="checkbox" className="mt-0.5" checked={removeMissing} onChange={(e) => setRemoveMissing(e.target.checked)} />
                  <span>
                    Also remove {preview.missing.length} {source || preview.source} holding{preview.missing.length === 1 ? '' : 's'} that {preview.missing.length === 1 ? "isn't" : "aren't"} in this
                    statement (sold since?): {preview.missing.slice(0, 5).map((m) => m.symbol || m.name).join(', ')}{preview.missing.length > 5 ? '…' : ''}
                  </span>
                </label>
              )}

              <label className="block text-xs text-slate-600 space-y-1">
                <span>Held since (optional, approximate)</span>
                <input type="date" value={heldSince} max={new Date().toISOString().slice(0, 10)} onChange={(e) => setHeldSince(e.target.value)} className={input} />
                <span className="block text-slate-400">
                  Statements don&apos;t include purchase dates. Give a rough date and Porulux estimates XIRR for holdings that have no dated lots (shown as approximate).
                  You can add real buy dates later; those take over.
                </span>
              </label>

              {error && <p className="text-sm text-red-600">{error}</p>}
              <div className="flex flex-wrap gap-2 items-center">
                <button onClick={onConfirm} disabled={busy || (selected.length === 0 && !(removeMissing && preview.missing.length))}
                  className="rounded-lg bg-indigo-600 text-white text-sm font-medium px-4 py-2 hover:bg-indigo-700 disabled:opacity-50">
                  {busy ? 'Saving…' : `Import ${selected.length} holding${selected.length === 1 ? '' : 's'}`}
                </button>
                <button onClick={reset} disabled={busy} className="rounded-lg border border-slate-300 text-sm px-4 py-2 text-slate-600">Cancel</button>
                <span className="text-xs text-slate-400">Nothing is saved until you click Import.</span>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
