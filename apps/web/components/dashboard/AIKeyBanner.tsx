'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { getAISettings, savePendingKeyIfAny } from '@/lib/api'

// Shown where AI extraction is used, only when the account has no key to run it with.
export default function AIKeyBanner() {
  const [needsKey, setNeedsKey] = useState(false)

  useEffect(() => {
    let live = true
    ;(async () => {
      await savePendingKeyIfAny()
      try {
        const s = await getAISettings()
        if (live) setNeedsKey(s.mode === 'none')
      } catch {}
    })()
    return () => { live = false }
  }, [])

  if (!needsKey) return null
  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 flex flex-wrap items-center justify-between gap-2">
      <span>Add your own Gemini or Claude API key to read payslips and PDF statements. CSV import works without one.</span>
      <Link href="/dashboard/settings" className="font-medium text-amber-900 underline">Add key</Link>
    </div>
  )
}
