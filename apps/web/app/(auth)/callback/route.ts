import { createServerClient, type CookieOptions } from '@supabase/ssr'
import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

import { publicOrigin, safeNext } from '@/lib/redirect'

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const origin = publicOrigin(request)
  const code = searchParams.get('code')
  const next = safeNext(searchParams.get('next'))

  // Supabase reports provider/link problems (denied consent, expired link) as query params.
  const providerError = searchParams.get('error_description') ?? searchParams.get('error')
  if (providerError) {
    return NextResponse.redirect(`${origin}/login?error=${encodeURIComponent(providerError)}`)
  }

  if (code) {
    const cookieStore = cookies()
    // Pre-build the redirect so we can attach session cookies onto it.
    const response = NextResponse.redirect(`${origin}${next}`)

    const supabase = createServerClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
      {
        cookies: {
          getAll() {
            return cookieStore.getAll()
          },
          setAll(cookiesToSet: { name: string; value: string; options: CookieOptions }[]) {
            // Write to both the Next.js cookie store and the redirect response
            // so the middleware sees the session on the very next request.
            cookiesToSet.forEach(({ name, value, options }) => {
              cookieStore.set(name, value, options)
              response.cookies.set(name, value, options)
            })
          },
        },
      },
    )

    const { error } = await supabase.auth.exchangeCodeForSession(code)
    if (!error) {
      return response
    }
    // PKCE links must be opened in the same browser that requested them.
    const msg = /code verifier|code challenge/i.test(error.message)
      ? 'Open the link in the same browser you used to request it, or request a new one.'
      : error.message
    return NextResponse.redirect(`${origin}/login?error=${encodeURIComponent(msg)}`)
  }

  return NextResponse.redirect(`${origin}/login?error=${encodeURIComponent('Sign-in link is invalid or has expired.')}`)
}
