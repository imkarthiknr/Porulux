'use client'

import Link from 'next/link'
import { useRef, useState } from 'react'

import { cleanKeyMessage, cleanPasswordMessage, isKeyError, isPasswordError } from '@/lib/api'

interface Props {
  label?: string
  accept?: string
  /** Runs the import. Resolve with a success message; throw to show an error. */
  onImport: (file: File, password?: string) => Promise<string>
  onDone?: () => void
}

// Picks a file, runs the import, and handles the two recoverable failures every statement upload
// can hit: a password-protected PDF and a missing/rejected AI key.
export default function FileImporter({ label = 'Import statement', accept = '.csv,.pdf,image/*', onImport, onDone }: Props) {
  const ref = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ text: string; kind: 'ok' | 'error' | 'info' } | null>(null)
  const [pending, setPending] = useState<File | null>(null)
  const [password, setPassword] = useState('')
  const [keyProblem, setKeyProblem] = useState(false)

  async function run(file: File, pw?: string) {
    setBusy(true)
    setMessage(null)
    setKeyProblem(false)
    try {
      const text = await onImport(file, pw)
      setMessage({ text, kind: 'ok' })
      setPending(null)
      setPassword('')
      onDone?.()
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Import failed'
      if (isPasswordError(msg)) {
        setPending(file)
        setMessage({ text: cleanPasswordMessage(msg), kind: 'info' })
      } else if (isKeyError(msg)) {
        setPending(null)
        setKeyProblem(true)
        setMessage({ text: cleanKeyMessage(msg), kind: 'error' })
      } else {
        setPending(null)
        setMessage({ text: msg, kind: 'error' })
      }
    } finally {
      setBusy(false)
      if (ref.current) ref.current.value = ''
    }
  }

  const tone = message?.kind === 'ok' ? 'text-green-600' : message?.kind === 'info' ? 'text-slate-600' : 'text-red-600'
  return (
    <div className="space-y-2">
      <input
        ref={ref} type="file" accept={accept} className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) { setPassword(''); run(f) } }}
      />
      <button
        onClick={() => ref.current?.click()} disabled={busy}
        className="rounded-lg bg-indigo-600 text-white text-sm font-medium px-4 py-2 hover:bg-indigo-700 disabled:opacity-50"
      >
        {busy ? 'Reading statement…' : label}
      </button>
      {busy && <p className="text-xs text-slate-500">PDFs can take up to a minute. CSV files are instant.</p>}

      {pending && !busy && (
        <form onSubmit={(e) => { e.preventDefault(); if (password) run(pending, password) }} className="flex flex-wrap items-center gap-2">
          <input
            type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="off" autoFocus
            placeholder={`Password for ${pending.name}`} aria-label="PDF password"
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
          />
          <button type="submit" disabled={!password} className="rounded-lg bg-indigo-600 text-white text-sm font-medium px-3 py-1.5 disabled:opacity-50">
            Unlock and import
          </button>
          <span className="text-xs text-slate-400">Used once to open the file, never stored.</span>
        </form>
      )}

      {message && !busy && (
        <p className={`text-sm ${tone}`}>
          {message.text}{' '}
          {keyProblem && <Link href="/dashboard/settings" className="underline font-medium">Open Settings</Link>}
        </p>
      )}
    </div>
  )
}
