'use client'

import { useState } from 'react'

import DashboardNav from '@/components/dashboard/DashboardNav'
import { submitFeedback, type FeedbackKind } from '@/lib/api'

const KINDS: { value: FeedbackKind; label: string; hint: string }[] = [
  { value: 'issue', label: 'Something is broken', hint: 'What did you do, what did you expect, and what happened instead?' },
  { value: 'idea', label: 'I have an idea', hint: 'What would you like Porulux to do?' },
  { value: 'question', label: 'I have a question', hint: 'What are you trying to do?' },
]

export default function FeedbackPage() {
  const [kind, setKind] = useState<FeedbackKind>('issue')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await submitFeedback(kind, message.trim(), document.referrer ? new URL(document.referrer).pathname : undefined)
      setSent(true)
      setMessage('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not send your feedback')
    } finally {
      setBusy(false)
    }
  }

  const current = KINDS.find((k) => k.value === kind)!

  return (
    <div className="min-h-screen bg-slate-50">
      <DashboardNav active="/dashboard/feedback" />
      <main className="max-w-2xl mx-auto px-6 py-8 space-y-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Help &amp; feedback</h1>
          <p className="text-sm text-slate-500 mt-0.5">Tell us what&apos;s wrong or what you&apos;d like. It goes straight to the team.</p>
        </div>

        <section className="bg-white rounded-2xl border border-slate-200 p-6">
          {sent ? (
            <div className="space-y-3">
              <p className="text-sm text-emerald-600 font-medium">Thanks, we&apos;ve received it.</p>
              <button onClick={() => setSent(false)} className="text-sm text-indigo-600 hover:underline">Send another</button>
            </div>
          ) : (
            <form onSubmit={onSubmit} className="space-y-4">
              <div className="flex flex-wrap gap-2">
                {KINDS.map((k) => (
                  <button
                    key={k.value}
                    type="button"
                    onClick={() => setKind(k.value)}
                    className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                      kind === k.value ? 'bg-indigo-600 border-indigo-600 text-white' : 'border-slate-200 text-slate-600 hover:border-slate-300'
                    }`}
                  >
                    {k.label}
                  </button>
                ))}
              </div>
              <div>
                <textarea
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  required
                  minLength={10}
                  maxLength={4000}
                  rows={7}
                  placeholder={current.hint}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
                <p className="text-xs text-slate-500 mt-1">Please don&apos;t include account numbers or other sensitive details.</p>
              </div>
              {error && <p className="text-sm text-red-600">{error}</p>}
              <button
                type="submit"
                disabled={busy || message.trim().length < 10}
                className="bg-indigo-600 text-white text-sm font-medium px-4 py-2 rounded-lg hover:bg-indigo-700 disabled:opacity-50"
              >
                {busy ? 'Sending…' : 'Send'}
              </button>
            </form>
          )}
        </section>
      </main>
    </div>
  )
}
