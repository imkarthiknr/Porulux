'use client'

import { useTheme, type Theme } from '@/lib/theme'

const Sun = () => (
  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
  </svg>
)
const Moon = () => (
  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
  </svg>
)
const Monitor = () => (
  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <rect x="3" y="4" width="18" height="12" rx="2" /><path d="M8 20h8M12 16v4" />
  </svg>
)

/** One-click light/dark switch (for headers and the login page). */
export function ThemeIconButton({ className = '' }: { className?: string }) {
  const { resolved, setTheme, mounted } = useTheme()
  const next = resolved === 'dark' ? 'light' : 'dark'
  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      aria-label={mounted ? `Switch to ${next} theme` : 'Toggle theme'}
      title={mounted ? `Switch to ${next} theme` : 'Toggle theme'}
      className={`w-9 h-9 shrink-0 rounded-full flex items-center justify-center text-slate-500 hover:text-slate-900 hover:bg-slate-100 transition-colors ${className}`}
    >
      {/* Same size before mount so the header doesn't shift */}
      {mounted ? (resolved === 'dark' ? <Sun /> : <Moon />) : <span className="w-[18px] h-[18px]" />}
    </button>
  )
}

const OPTIONS: { value: Theme; label: string; icon: React.ReactNode }[] = [
  { value: 'system', label: 'System', icon: <Monitor /> },
  { value: 'light', label: 'Light', icon: <Sun /> },
  { value: 'dark', label: 'Dark', icon: <Moon /> },
]

/** System / Light / Dark chooser (for menus and Settings). "System" follows the OS and updates live. */
export function ThemeSegmented() {
  const { theme, setTheme, mounted } = useTheme()
  return (
    <div role="radiogroup" aria-label="Theme" className="grid grid-cols-3 gap-1 rounded-lg bg-slate-100 p-1">
      {OPTIONS.map((o) => {
        const active = mounted && theme === o.value
        return (
          <button
            key={o.value} type="button" role="radio" aria-checked={active} onClick={() => setTheme(o.value)}
            className={`flex items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-colors ${
              active ? 'bg-white dark:bg-slate-200 text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            {o.icon}{o.label}
          </button>
        )
      })}
    </div>
  )
}
