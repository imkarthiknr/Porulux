'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase'

export default function CallbackPage() {
  const router = useRouter()

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const code = params.get('code')
    const next = params.get('next') ?? '/dashboard'

    async function exchange() {
      const supabase = createClient()
      if (code) {
        const { error } = await supabase.auth.exchangeCodeForSession(code)
        if (!error) {
          router.replace(next)
          return
        }
      }
      router.replace('/login?error=callback_error')
    }

    exchange()
  }, [router])

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center">
      <p className="text-slate-500 text-sm">Signing you in…</p>
    </div>
  )
}
