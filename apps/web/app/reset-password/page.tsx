'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { ThemeIconButton } from '@/components/ThemeToggle'
import { createClient } from '@/lib/supabase'

export default function ResetPasswordPage() {
  const [supabase] = useState(() => createClient())
  const [ready, setReady] = useState<boolean | null>(null)
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  // /callback has already exchanged the emailed code for a session by the time we land here.
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setReady(!!data.session))
  }, [supabase])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (password.length < 8) return setError('Password must be at least 8 characters.')
    if (password !== confirm) return setError('Passwords do not match.')
    setLoading(true)
    const { error } = await supabase.auth.updateUser({ password })
    setLoading(false)
    if (error) return setError(error.message)
    setDone(true)
    setTimeout(() => window.location.assign('/dashboard'), 1500)
  }

  const input =
    'w-full px-3 py-2.5 border border-slate-300 rounded-lg text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent'

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="fixed top-3 right-3"><ThemeIconButton /></div>
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <p className="text-3xl font-bold text-indigo-600 tracking-tight">₹ Porulux</p>
        </div>
        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-8">
          <h1 className="text-xl font-semibold text-slate-900 mb-6">Set a new password</h1>

          {ready === null && <p className="text-sm text-slate-400">Checking your link…</p>}

          {ready === false && (
            <div className="space-y-4 text-sm text-slate-600">
              <p>This reset link is invalid or has expired. Request a new one from the sign-in page.</p>
              <Link href="/login" className="text-indigo-600 font-medium hover:underline">Back to sign in</Link>
            </div>
          )}

          {ready && done && <p className="text-sm text-green-600">Password updated. Redirecting…</p>}

          {ready && !done && (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label htmlFor="pw" className="block text-sm font-medium text-slate-700 mb-1.5">New password</label>
                <input id="pw" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 8 characters" minLength={8} required autoComplete="new-password" className={input} />
              </div>
              <div>
                <label htmlFor="pw2" className="block text-sm font-medium text-slate-700 mb-1.5">Confirm password</label>
                <input id="pw2" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)}
                  required autoComplete="new-password" className={input} />
              </div>
              {error && <p className="text-sm text-red-600">{error}</p>}
              <button type="submit" disabled={loading || !password || !confirm}
                className="w-full py-2.5 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
                {loading ? 'Please wait…' : 'Update password'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
