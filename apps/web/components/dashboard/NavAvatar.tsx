'use client'

import Link from 'next/link'
import { useEffect, useRef, useState } from 'react'

import { signOut } from '@/app/actions'
import { ThemeSegmented } from '@/components/ThemeToggle'
import { getProfile, type Profile } from '@/lib/api'

export default function NavAvatar({ email }: { email?: string }) {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    getProfile().then(setProfile).catch(() => {})
  }, [])

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [open])

  const name = profile?.full_name || email || profile?.email || 'Account'
  const initial = name.trim().charAt(0).toUpperCase() || '?'

  async function onSignOut() {
    setBusy(true)
    try { await signOut() } finally { window.location.assign('/login') }
  }

  const item = 'block w-full text-left px-4 py-2 text-sm text-slate-700 hover:bg-slate-50'
  return (
    <div className="relative shrink-0" ref={ref}>
      <button
        onClick={() => setOpen(!open)} aria-haspopup="menu" aria-expanded={open} aria-label="Account menu"
        className="w-9 h-9 rounded-full overflow-hidden bg-indigo-100 text-indigo-700 text-sm font-semibold flex items-center justify-center ring-2 ring-white hover:ring-indigo-200"
      >
        {profile?.avatar_url
          // eslint-disable-next-line @next/next/no-img-element
          ? <img src={profile.avatar_url} alt="" className="w-full h-full object-cover" />
          : initial}
      </button>
      {open && (
        <div role="menu" className="absolute right-0 mt-2 w-60 rounded-xl bg-white border border-slate-200 shadow-lg py-1 z-20">
          <div className="px-4 py-3 border-b border-slate-100">
            <p className="text-sm font-medium text-slate-900 truncate">{profile?.full_name || 'Your profile'}</p>
            <p className="text-xs text-slate-500 truncate">{email || profile?.email}</p>
          </div>
          <Link href="/dashboard/profile" className={item} onClick={() => setOpen(false)}>Profile</Link>
          <Link href="/dashboard/settings" className={item} onClick={() => setOpen(false)}>Settings & AI key</Link>
          <div className="px-3 py-2 border-t border-slate-100">
            <p className="text-[11px] uppercase tracking-wide text-slate-400 mb-1.5 px-1">Theme</p>
            <ThemeSegmented />
          </div>
          <button onClick={onSignOut} disabled={busy} className={`${item} border-t border-slate-100 text-red-600`}>
            {busy ? 'Signing out…' : 'Sign out'}
          </button>
        </div>
      )}
    </div>
  )
}
