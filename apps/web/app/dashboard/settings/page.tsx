'use client'

import { useCallback, useEffect, useState } from 'react'

import DashboardNav from '@/components/dashboard/DashboardNav'
import { deleteAIKey, getAISettings, saveAIKey, savePendingKeyIfAny, type AISettings } from '@/lib/api'

const PROVIDERS = [
  {
    value: 'gemini' as const,
    label: 'Google Gemini',
    help: 'Free tier available. Create a key at aistudio.google.com/apikey',
    link: 'https://aistudio.google.com/apikey',
  },
  {
    value: 'anthropic' as const,
    label: 'Anthropic Claude',
    help: 'Pay-as-you-go. Create a key at console.anthropic.com → API keys',
    link: 'https://console.anthropic.com/settings/keys',
  },
]

export default function SettingsPage() {
  const [settings, setSettings] = useState<AISettings | null>(null)
  const [provider, setProvider] = useState<'gemini' | 'anthropic'>('gemini')
  const [apiKey, setApiKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      // A key typed on the sign-up form (same tab) is saved now that we have a session.
      if (await savePendingKeyIfAny()) setNotice('Your API key from sign-up was verified and saved.')
      setSettings(await getAISettings())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load settings')
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function onSave(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      setSettings(await saveAIKey(provider, apiKey.trim()))
      setApiKey('')
      setNotice('Key verified and saved. Uploads will now use it.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the key')
    } finally {
      setBusy(false)
    }
  }

  async function onRemove() {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      await deleteAIKey()
      setSettings(await getAISettings())
      setNotice('Key removed.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not remove the key')
    } finally {
      setBusy(false)
    }
  }

  const current = PROVIDERS.find((p) => p.value === provider)!
  const input = 'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500'

  return (
    <div className="min-h-screen bg-slate-50">
      <DashboardNav active="/dashboard/settings" />
      <main className="max-w-2xl mx-auto px-6 py-8 space-y-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Settings</h1>
          <p className="text-sm text-slate-500 mt-0.5">AI document extraction runs on your own API key.</p>
        </div>

        <section className="bg-white rounded-2xl border border-slate-200 p-6 space-y-5">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">AI provider key</h2>
            <p className="text-xs text-slate-500 mt-1">
              Used to read payslips and PDF/image bank statements. CSV imports and everything else work without it.
              Your key is verified, then stored encrypted on the server. It is never shown again or sent back to your browser.
            </p>
          </div>

          {settings && (
            <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-3 text-sm flex items-center justify-between gap-3">
              <span className="text-slate-700">
                {settings.mode === 'own' && <>Using your {settings.provider === 'anthropic' ? 'Claude' : 'Gemini'} key ending <strong>…{settings.key_last4}</strong></>}
                {settings.mode === 'shared' && <>Using the shared app key (existing account). You can switch to your own key below.</>}
                {settings.mode === 'none' && <span className="text-amber-700">No key yet. Add one to enable document uploads.</span>}
              </span>
              {settings.mode === 'own' && (
                <button onClick={onRemove} disabled={busy} className="text-xs text-red-500 hover:text-red-700 shrink-0">Remove</button>
              )}
            </div>
          )}

          <form onSubmit={onSave} className="space-y-4">
            <div className="flex gap-2">
              {PROVIDERS.map((p) => (
                <button
                  type="button" key={p.value} onClick={() => setProvider(p.value)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    provider === p.value ? 'bg-indigo-600 text-white' : 'bg-white border border-slate-200 text-slate-600 hover:border-indigo-300'
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
            <label className="block text-xs text-slate-600 space-y-1">
              <span>
                {current.label} API key{' '}
                <a href={current.link} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">Get a key ↗</a>
              </span>
              <input
                type="password" className={input} value={apiKey} onChange={(e) => setApiKey(e.target.value)}
                placeholder={provider === 'gemini' ? 'AIza…' : 'sk-ant-…'} autoComplete="off" required minLength={20}
              />
              <span className="block text-slate-400">{current.help}</span>
            </label>
            {error && <p className="text-sm text-red-600">{error}</p>}
            {notice && <p className="text-sm text-green-600">{notice}</p>}
            <button
              type="submit" disabled={busy || apiKey.trim().length < 20}
              className="rounded-lg bg-indigo-600 text-white text-sm font-medium px-4 py-2 hover:bg-indigo-700 disabled:opacity-50"
            >
              {busy ? 'Verifying…' : settings?.mode === 'own' ? 'Replace key' : 'Verify and save key'}
            </button>
          </form>
        </section>
      </main>
    </div>
  )
}
