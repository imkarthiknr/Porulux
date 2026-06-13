'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase'

export default function CallbackPage() {
  const router = useRouter()

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const next = params.get('next') ?? '/dashboard'

    async function handleCallback() {
      const supabase = createClient()
      // Implicit flow: supabase-js detects the session from the URL hash automatically.
      // Give it a moment to process the hash before calling getSession.
      const { data: { session } } = await supabase.auth.getSession()
      if (session) {
        router.replace(next)
      } else {
        router.replace('/login?error=no_session')
      }
    }

    handleCallback()
  }, [router])

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center">
      <p className="text-slate-500 text-sm">Signing you in…</p>
    </div>
  )
}
