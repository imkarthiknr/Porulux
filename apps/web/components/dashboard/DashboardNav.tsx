import Link from 'next/link'

import NavAvatar from '@/components/dashboard/NavAvatar'
import { ThemeIconButton } from '@/components/ThemeToggle'

const LINKS = [
  { href: '/dashboard', label: 'Dashboard' },
  { href: '/dashboard/transactions', label: 'Transactions' },
  { href: '/dashboard/banks', label: 'Banks' },
  { href: '/dashboard/cards', label: 'Cards' },
  { href: '/dashboard/salary', label: 'Salary' },
  { href: '/dashboard/investments', label: 'Investments' },
  { href: '/dashboard/loans', label: 'Loans' },
  { href: '/dashboard/accounts', label: 'Accounts' },
]

export default function DashboardNav({ active, email }: { active: string; email?: string }) {
  // Profile and Settings live in the avatar menu, so nothing in the bar is highlighted for them.
  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
      <div className="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between gap-4">
        <Link href="/dashboard" className="text-lg font-bold text-indigo-600 tracking-tight shrink-0">₹ Porulux</Link>
        <nav className="flex items-center gap-5 overflow-x-auto flex-1 justify-end">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={`text-sm font-medium whitespace-nowrap transition-colors ${
                l.href === active ? 'text-indigo-600' : 'text-slate-500 hover:text-slate-900'
              }`}
            >
              {l.label}
            </Link>
          ))}
          <Link
            href="/dashboard/upload"
            className={`text-sm font-medium whitespace-nowrap rounded-lg px-3 py-1.5 ${
              active === '/dashboard/upload' ? 'bg-indigo-600 text-white' : 'bg-indigo-50 text-indigo-700 hover:bg-indigo-100'
            }`}
          >
            + Upload
          </Link>
        </nav>
        <ThemeIconButton />
        <NavAvatar email={email} />
      </div>
    </header>
  )
}
