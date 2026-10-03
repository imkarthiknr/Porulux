'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

import DashboardNav from '@/components/dashboard/DashboardNav'
import { deleteAvatar, getProfile, saveProfile, uploadAvatar, type Profile } from '@/lib/api'

const FIELDS = [
  { name: 'full_name', label: 'Full name', span: 'md:col-span-2', autoComplete: 'name' },
  { name: 'phone', label: 'Contact number', placeholder: '+91 98765 43210', autoComplete: 'tel' },
  { name: 'address_line1', label: 'Address line 1', span: 'md:col-span-2', autoComplete: 'address-line1' },
  { name: 'address_line2', label: 'Address line 2', span: 'md:col-span-2', autoComplete: 'address-line2' },
  { name: 'city', label: 'City', autoComplete: 'address-level2' },
  { name: 'state', label: 'State', autoComplete: 'address-level1' },
  { name: 'postal_code', label: 'PIN / postal code', autoComplete: 'postal-code' },
  { name: 'country', label: 'Country', autoComplete: 'country-name' },
] as const

type FormState = Record<(typeof FIELDS)[number]['name'], string>

const toForm = (p: Profile): FormState => ({
  full_name: p.full_name ?? '', phone: p.phone ?? '', address_line1: p.address_line1 ?? '', address_line2: p.address_line2 ?? '',
  city: p.city ?? '', state: p.state ?? '', postal_code: p.postal_code ?? '', country: p.country ?? 'India',
})

export default function ProfilePage() {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [form, setForm] = useState<FormState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [photoBusy, setPhotoBusy] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    try {
      const p = await getProfile()
      setProfile(p)
      setForm(toForm(p))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load profile')
    }
  }, [])
  useEffect(() => { load() }, [load])

  async function onSave(e: React.FormEvent) {
    e.preventDefault()
    if (!form) return
    setSaving(true)
    setError(null)
    setNotice(null)
    try {
      const p = await saveProfile(form)
      setProfile(p)
      setForm(toForm(p))
      setNotice('Profile saved.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save')
    } finally {
      setSaving(false)
    }
  }

  async function onPhoto(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setPhotoBusy(true)
    setError(null)
    setNotice(null)
    try {
      setProfile(await uploadAvatar(file))
      setNotice('Photo updated.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not upload the photo')
    } finally {
      setPhotoBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  async function onRemovePhoto() {
    setPhotoBusy(true)
    try { setProfile(await deleteAvatar()) } catch (err) { setError(err instanceof Error ? err.message : 'Could not remove the photo') } finally { setPhotoBusy(false) }
  }

  const initial = (profile?.full_name || profile?.email || '?').trim().charAt(0).toUpperCase()
  const input = 'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500'

  return (
    <div className="min-h-screen bg-slate-50">
      <DashboardNav active="/dashboard/profile" />
      <main className="max-w-2xl mx-auto px-6 py-8 space-y-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Profile</h1>
          <p className="text-sm text-slate-500 mt-0.5">Your details. They stay private to your account.</p>
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}
        {notice && <p className="text-sm text-green-600">{notice}</p>}

        <section className="bg-white rounded-2xl border border-slate-200 p-6 flex items-center gap-5">
          <div className="w-20 h-20 rounded-full overflow-hidden bg-indigo-100 text-indigo-700 text-3xl font-semibold flex items-center justify-center shrink-0">
            {profile?.avatar_url
              // eslint-disable-next-line @next/next/no-img-element
              ? <img src={profile.avatar_url} alt="Your profile photo" className="w-full h-full object-cover" />
              : initial}
          </div>
          <div className="space-y-2">
            <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" onChange={onPhoto} className="hidden" />
            <div className="flex gap-2">
              <button onClick={() => fileRef.current?.click()} disabled={photoBusy}
                className="rounded-lg bg-indigo-600 text-white text-sm font-medium px-4 py-2 hover:bg-indigo-700 disabled:opacity-50">
                {photoBusy ? 'Working…' : profile?.avatar_url ? 'Change photo' : 'Upload photo'}
              </button>
              {profile?.avatar_url && (
                <button onClick={onRemovePhoto} disabled={photoBusy} className="rounded-lg border border-slate-300 text-sm px-4 py-2 text-slate-600 hover:border-red-300 hover:text-red-600">
                  Remove
                </button>
              )}
            </div>
            <p className="text-xs text-slate-400">JPEG, PNG or WebP, up to 2 MB.</p>
          </div>
        </section>

        <form onSubmit={onSave} className="bg-white rounded-2xl border border-slate-200 p-6 space-y-4">
          <label className="block text-xs text-slate-600 space-y-1">
            <span>Email</span>
            <input className={`${input} bg-slate-50 text-slate-500`} value={profile?.email ?? ''} readOnly />
          </label>
          {!form ? (
            <p className="text-sm text-slate-400">Loading…</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {FIELDS.map((f) => (
                <label key={f.name} className={`text-xs text-slate-600 space-y-1 ${'span' in f ? f.span : ''}`}>
                  <span>{f.label}</span>
                  <input
                    className={input} value={form[f.name]} autoComplete={f.autoComplete}
                    placeholder={'placeholder' in f ? f.placeholder : undefined}
                    onChange={(e) => setForm({ ...form, [f.name]: e.target.value })}
                  />
                </label>
              ))}
            </div>
          )}
          <button type="submit" disabled={saving || !form} className="rounded-lg bg-indigo-600 text-white text-sm font-medium px-4 py-2 hover:bg-indigo-700 disabled:opacity-50">
            {saving ? 'Saving…' : 'Save profile'}
          </button>
        </form>
      </main>
    </div>
  )
}
