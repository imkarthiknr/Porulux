'use client'

import { useCallback, useEffect, useState } from 'react'

export type Theme = 'light' | 'dark' | 'system'
export type ResolvedTheme = 'light' | 'dark'

export const THEME_KEY = 'porulux.theme'
const CHANGE_EVENT = 'porulux-theme'

// The same logic runs before first paint in the inline script in app/layout.tsx; keep them in step.
export function readStoredTheme(): Theme {
  try {
    const v = localStorage.getItem(THEME_KEY)
    return v === 'light' || v === 'dark' ? v : 'system'
  } catch {
    return 'system'
  }
}

export function resolveTheme(theme: Theme): ResolvedTheme {
  if (theme !== 'system') return theme
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(theme: Theme): ResolvedTheme {
  const resolved = resolveTheme(theme)
  const root = document.documentElement
  root.classList.toggle('dark', resolved === 'dark')
  root.style.colorScheme = resolved // native controls (selects, date pickers, scrollbars) follow
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', resolved === 'dark' ? '#020617' : '#f8fafc')
  return resolved
}

export function useTheme() {
  // Server and first client render agree on these defaults; the real values land after mount, which
  // avoids a hydration mismatch (the page itself is already the right colour thanks to the inline script).
  const [theme, setThemeState] = useState<Theme>('system')
  const [resolved, setResolved] = useState<ResolvedTheme>('light')
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    const sync = () => {
      const t = readStoredTheme()
      setThemeState(t)
      setResolved(applyTheme(t))
    }
    sync()
    setMounted(true)
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    window.addEventListener('storage', sync)        // another tab changed it
    window.addEventListener(CHANGE_EVENT, sync)     // another toggle on this page changed it
    mq.addEventListener('change', sync)             // OS switched while on "system"
    return () => {
      window.removeEventListener('storage', sync)
      window.removeEventListener(CHANGE_EVENT, sync)
      mq.removeEventListener('change', sync)
    }
  }, [])

  const setTheme = useCallback((t: Theme) => {
    try {
      if (t === 'system') localStorage.removeItem(THEME_KEY)
      else localStorage.setItem(THEME_KEY, t)
    } catch { /* private mode: still apply for this session */ }
    window.dispatchEvent(new Event(CHANGE_EVENT))
  }, [])

  return { theme, resolved, setTheme, mounted }
}
