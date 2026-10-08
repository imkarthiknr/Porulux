// Same mark as app/icon.svg (the favicon), inlined so it needs no extra request.
export default function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width={size} height={size} aria-hidden="true">
      <defs>
        <linearGradient id="porulux-logo-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#6366f1" />
          <stop offset="1" stopColor="#4338ca" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="15" fill="url(#porulux-logo-g)" />
      <path d="M22 50V15h12.5a10.5 10.5 0 0 1 0 21H22" fill="none" stroke="#fff" strokeWidth="8" strokeLinejoin="round" strokeLinecap="round" />
      <path d="M36 52l7-8 5 4 9-12" fill="none" stroke="#34d399" strokeWidth="5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}
