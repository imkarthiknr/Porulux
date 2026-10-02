'use server'

import { createServerClient, type CookieOptions } from '@supabase/ssr'
import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'

function serverSupabase() {
  const cookieStore = cookies()
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() { return cookieStore.getAll() },
        setAll(cookiesToSet: { name: string; value: string; options: CookieOptions }[]) {
          cookiesToSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options),
          )
        },
      },
    },
  )
}

export async function signIn(email: string, password: string) {
  const supabase = serverSupabase()
  const { error } = await supabase.auth.signInWithPassword({ email, password })
  if (error) return { error: error.message }
  redirect('/dashboard')
}

export async function signUp(email: string, password: string, origin: string) {
  const supabase = serverSupabase()
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    // Confirmation links must land on /callback so the code is exchanged for a session.
    options: { emailRedirectTo: `${origin}/callback` },
  })
  if (error) return { error: error.message }
  // Supabase hides duplicate emails: it returns a user with no identities and sends nothing.
  if (data.user && data.user.identities?.length === 0) {
    return { error: 'An account with this email already exists. Sign in or reset your password.' }
  }
  // Email confirmation enabled: no session yet.
  if (!data.session) {
    return { notice: 'Account created. Check your inbox and click the confirmation link to continue.' }
  }
  redirect('/dashboard')
}
