import Link from 'next/link'

const LINKS = [
  { href: '/dashboard', label: 'Dashboard' },
  { href: '/dashboard/accounts', label: 'Accounts' },
  { href: '/dashboard/transactions', label: 'Transactions' },
  { href: '/dashboard/salary', label: 'Salary' },
  { href: '/dashboard/upload', label: '+ Upload' },
]

export default function DashboardNav({ active, email }: { active: string; email?: string }) {
  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
      <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between gap-4">
        <span className="text-lg font-bold text-indigo-600 tracking-tight">₹ Porulux</span>
        <nav className="flex items-center gap-5 overflow-x-auto">
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
          {email && <span className="hidden md:inline text-sm text-slate-400">{email}</span>}
        </nav>
      </div>
    </header>
  )
}
