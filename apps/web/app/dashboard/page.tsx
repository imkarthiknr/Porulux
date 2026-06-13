import { createServerClient, type CookieOptions } from '@supabase/ssr'
import { cookies } from 'next/headers'
import Link from 'next/link'
import { redirect } from 'next/navigation'
import SummaryCard from '@/components/dashboard/SummaryCard'
import NetWorthChart from '@/components/dashboard/NetWorthChart'
import AssetBreakdownChart from '@/components/dashboard/AssetBreakdownChart'

// ── Types ──────────────────────────────────────────────────────────────────────

interface Breakdown {
  investments: number
  epf_nps: number
  bank_balance: number
  loans: number
}

interface Snapshot {
  total_assets: number
  total_liabilities: number
  net_worth: number
  breakdown: Breakdown
}

interface HistoryEntry {
  id: string
  snapshot_date: string
  net_worth: number
  breakdown: Breakdown
}

// ── Data fetching ──────────────────────────────────────────────────────────────

async function fetchJSON<T>(path: string, token: string): Promise<T> {
  const base = process.env.API_URL ?? 'http://localhost:8000'
  const res = await fetch(`${base}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store',
  })
  if (!res.ok) throw new Error(`${path} returned ${res.status}`)
  return res.json() as Promise<T>
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default async function DashboardPage() {
  const cookieStore = cookies()

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll()
        },
        setAll(cookiesToSet: { name: string; value: string; options: CookieOptions }[]) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options),
            )
          } catch {}
        },
      },
    },
  )

  const {
    data: { session },
  } = await supabase.auth.getSession()

  if (!session) redirect('/login')

  const [snapshot, history] = await Promise.all([
    fetchJSON<Snapshot>('/api/v1/networth/snapshot', session.access_token),
    fetchJSON<HistoryEntry[]>('/api/v1/networth/history', session.access_token),
  ])

  // Monthly change: current net worth vs. the second-most-recent saved snapshot.
  // History is sorted DESC, so history[1] is the previous snapshot.
  const prevNetWorth = history[1]?.net_worth ?? history[0]?.net_worth ?? snapshot.net_worth
  const monthlyChange = snapshot.net_worth - prevNetWorth
  const monthlyChangePct =
    prevNetWorth !== 0 ? (monthlyChange / Math.abs(prevNetWorth)) * 100 : 0

  return (
    <div className="min-h-screen bg-slate-50">
      {/* ── Header ── */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <span className="text-lg font-bold text-indigo-600 tracking-tight">₹ Porulux</span>
          <div className="flex items-center gap-4">
            <Link
              href="/dashboard/upload"
              className="text-sm font-medium text-indigo-600 hover:text-indigo-700 transition-colors"
            >
              + Upload
            </Link>
            <span className="text-sm text-slate-500">{session.user.email}</span>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8 space-y-8">
        {/* ── Page title ── */}
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Dashboard</h1>
          <p className="text-sm text-slate-500 mt-0.5">Your complete financial picture</p>
        </div>

        {/* ── Summary cards ── */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <SummaryCard
            label="Total Assets"
            value={snapshot.total_assets}
            variant="asset"
          />
          <SummaryCard
            label="Total Liabilities"
            value={snapshot.total_liabilities}
            variant="liability"
          />
          <SummaryCard
            label="Net Worth"
            value={snapshot.net_worth}
            variant="networth"
          />
          <SummaryCard
            label="Monthly Change"
            value={monthlyChange}
            variant="change"
            changePct={monthlyChangePct}
          />
        </div>

        {/* ── Charts ── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 p-6">
            <h2 className="text-sm font-semibold text-slate-900 mb-5">Net Worth Trend</h2>
            <NetWorthChart history={history} />
          </div>

          <div className="bg-white rounded-2xl border border-slate-200 p-6">
            <h2 className="text-sm font-semibold text-slate-900 mb-5">Asset Breakdown</h2>
            <AssetBreakdownChart breakdown={snapshot.breakdown} />
          </div>
        </div>
      </main>
    </div>
  )
}
