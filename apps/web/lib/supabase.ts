import { createBrowserClient } from '@supabase/ssr'

// Used in Client Components only.
// For Server Components and Route Handlers, create the client inline using
// createServerClient from @supabase/ssr with the request cookies.
export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    { auth: { flowType: 'implicit' } },
  )
}
