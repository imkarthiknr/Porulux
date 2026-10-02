import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'

type CookieToSet = { name: string; value: string; options?: Record<string, unknown> }

export async function middleware(request: NextRequest) {
  // Mutable response — the Supabase client may rewrite session cookies on it.
  let supabaseResponse = NextResponse.next({ request })
  let cacheHeaders: Record<string, string> = {}

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll()
        },
        setAll(cookiesToSet: CookieToSet[], headers: Record<string, string>) {
          // Propagate refreshed cookies onto both the forwarded request and
          // the response so that downstream server components see them too.
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value))
          supabaseResponse = NextResponse.next({ request })
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options),
          )
          // Cache-Control etc. so a CDN never caches a response carrying a session cookie.
          cacheHeaders = headers ?? {}
          Object.entries(cacheHeaders).forEach(([k, v]) => supabaseResponse.headers.set(k, v))
        },
      },
    },
  )

  // IMPORTANT: use getUser(), not getSession(). getSession() reads from the
  // cookie without re-validating with the Auth server and is unsafe here.
  const {
    data: { user },
  } = await supabase.auth.getUser()

  if (!user && request.nextUrl.pathname.startsWith('/dashboard')) {
    const loginUrl = request.nextUrl.clone()
    loginUrl.pathname = '/login'
    loginUrl.search = ''
    loginUrl.searchParams.set('next', request.nextUrl.pathname)
    const redirect = NextResponse.redirect(loginUrl)
    // Keep any cookies Supabase just cleared/refreshed.
    supabaseResponse.cookies.getAll().forEach((c) => redirect.cookies.set(c))
    Object.entries(cacheHeaders).forEach(([k, v]) => redirect.headers.set(k, v))
    return redirect
  }

  return supabaseResponse
}

export const config = {
  matcher: [
    // Skip /api/* (proxied to FastAPI, which validates the bearer token itself; also avoids
    // middleware body buffering on file uploads) plus Next.js internals and static files.
    '/((?!api/|_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
}
