import type { Config } from 'tailwindcss'

// Neutral greys come from CSS variables (see app/globals.css), so every existing slate-* class flips with the
// theme without touching components. Coloured tints (indigo/red/amber/emerald) are adjusted in globals.css.
const slateVar = (n: number) => `rgb(var(--slate-${n}) / <alpha-value>)`

const config: Config = {
  darkMode: 'class',
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './lib/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        slate: Object.fromEntries([50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950].map((n) => [n, slateVar(n)])),
      },
    },
  },
  plugins: [],
}

export default config
