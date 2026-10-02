/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    // AI document extraction can take well over the 30s default
    proxyTimeout: 120_000,
  },
  // Same-origin API: the browser calls /api/* on this site and Next forwards it
  // to the FastAPI service, so no CORS and no second public hostname for the client.
  async rewrites() {
    const api = process.env.API_URL
    if (!api) return []
    return [{ source: '/api/:path*', destination: `${api.replace(/\/$/, '')}/api/:path*` }]
  },
}

export default nextConfig
