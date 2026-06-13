function Bone({ className }: { className?: string }) {
  return <div className={`bg-slate-200 rounded animate-pulse ${className}`} />
}

function CardSkeleton() {
  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-2">
      <Bone className="h-3 w-24" />
      <Bone className="h-7 w-36" />
    </div>
  )
}

export default function DashboardLoading() {
  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <Bone className="h-6 w-28" />
          <Bone className="h-4 w-40" />
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8 space-y-8">
        {/* Title */}
        <div className="space-y-1.5">
          <Bone className="h-7 w-36" />
          <Bone className="h-4 w-52" />
        </div>

        {/* Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>

        {/* Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 p-6 space-y-4">
            <Bone className="h-4 w-32" />
            <Bone className="h-64 w-full rounded-lg" />
          </div>
          <div className="bg-white rounded-2xl border border-slate-200 p-6 space-y-4">
            <Bone className="h-4 w-32" />
            <Bone className="h-44 w-44 rounded-full mx-auto" />
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="flex justify-between">
                  <Bone className="h-3 w-24" />
                  <Bone className="h-3 w-16" />
                </div>
              ))}
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
