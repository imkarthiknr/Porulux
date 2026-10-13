'use client'

import { useEffect, useRef, useState } from 'react'

const DEFAULT_SIZES = [10, 25, 50, 100]

export interface PageState<T> {
  items: T[]            // rows for the current page
  page: number          // 1-based
  pageCount: number
  pageSize: number
  total: number
  /** Index of items[0] within the full list, for callers that edit rows by position. */
  startIndex: number
  setPage: (p: number) => void
  setPageSize: (n: number) => void
  sizes: number[]
}

/**
 * Client-side paging over a list that is already loaded. The page snaps back to 1 when `resetKey` changes
 * (a new filter or month) and is clamped when rows are removed, so you never land on an empty page.
 * `initialPage` is only used for the first render.
 */
export function usePagination<T>(
  rows: T[],
  { pageSize: initialSize = 25, sizes = DEFAULT_SIZES, resetKey = '', initialPage = 1 }: { pageSize?: number; sizes?: number[]; resetKey?: string; initialPage?: number } = {},
): PageState<T> {
  const [pageSize, setPageSizeState] = useState(initialSize)
  const [page, setPageState] = useState(initialPage)
  const total = rows.length
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const safePage = Math.min(Math.max(1, page), pageCount)

  const lastKey = useRef(resetKey)
  useEffect(() => {
    if (lastKey.current !== resetKey) { lastKey.current = resetKey; setPageState(1) }
  }, [resetKey])

  const startIndex = (safePage - 1) * pageSize
  return {
    items: rows.slice(startIndex, startIndex + pageSize),
    page: safePage, pageCount, pageSize, total, startIndex, sizes,
    setPage: (p) => setPageState(Math.min(Math.max(1, p), pageCount)),
    setPageSize: (n) => { setPageSizeState(n); setPageState(1) },
  }
}

// 1 … 4 5 6 … 20 : first, last, and a window around the current page.
function pageList(page: number, count: number): (number | '…')[] {
  const keep = new Set([1, count, page - 1, page, page + 1])
  const out: (number | '…')[] = []
  let prev = 0
  for (const n of Array.from(keep).filter((n) => n >= 1 && n <= count).sort((a, b) => a - b)) {
    if (n - prev > 1) out.push('…')
    out.push(n)
    prev = n
  }
  return out
}

export default function Pagination<T>({ state, label = 'rows' }: { state: PageState<T>; label?: string }) {
  const { page, pageCount, pageSize, total, startIndex, setPage, setPageSize, sizes } = state
  // Nothing to page through: stay out of the way.
  if (total <= Math.min(...sizes)) return null

  const from = startIndex + 1
  const to = Math.min(startIndex + pageSize, total)
  const btn = 'min-w-[2rem] h-8 px-2 rounded-lg border text-xs transition-colors disabled:opacity-40 disabled:cursor-not-allowed'
  const idle = 'border-slate-200 text-slate-600 hover:border-slate-300'

  return (
    <nav aria-label="Pagination" className="flex flex-wrap items-center justify-between gap-3 pt-3 text-xs text-slate-500">
      <p>Showing {from}–{to} of {total} {label}</p>
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-1.5">
          <span>Per page</span>
          <select
            value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))}
            className="h-8 rounded-lg border border-slate-200 bg-white px-1.5 text-xs text-slate-700"
          >
            {Array.from(new Set([...sizes, pageSize])).sort((a, b) => a - b).map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <div className="flex items-center gap-1">
          <button type="button" onClick={() => setPage(page - 1)} disabled={page <= 1} className={`${btn} ${idle}`} aria-label="Previous page">‹</button>
          {pageList(page, pageCount).map((n, i) => n === '…'
            ? <span key={`gap${i}`} className="px-1">…</span>
            : (
              <button
                key={n} type="button" onClick={() => setPage(n)} aria-current={n === page ? 'page' : undefined}
                className={`${btn} ${n === page ? 'bg-indigo-600 border-indigo-600 text-white' : idle}`}
              >
                {n}
              </button>
            ))}
          <button type="button" onClick={() => setPage(page + 1)} disabled={page >= pageCount} className={`${btn} ${idle}`} aria-label="Next page">›</button>
        </div>
      </div>
    </nav>
  )
}
