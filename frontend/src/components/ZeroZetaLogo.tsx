// src/components/ZeroZetaLogo.tsx — v4.0.3
// Inline SVG recreation of the ZeroZeta logo.
// Used in sidebar, login, and register pages.

interface ZeroZetaLogoProps {
  size?: 'sm' | 'md' | 'lg'
  variant?: 'dark' | 'light'   // dark = for white backgrounds, light = for dark sidebar
}

const SIZE_MAP = {
  sm: { width: 90,  height: 18 },
  md: { width: 120, height: 24 },
  lg: { width: 160, height: 32 },
}

export default function ZeroZetaLogo({ size = 'md', variant = 'dark' }: ZeroZetaLogoProps) {
  const { width, height } = SIZE_MAP[size]
  const textColor = variant === 'light' ? '#ffffff' : '#111111'
  const green     = '#22c55e'

  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 160 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-label="ZeroZeta"
    >
      {/* Zeta symbol — stylised curved Z */}
      <path
        d="M6 6 C6 6 18 6 20 6 C22 6 22 8 20 10 L8 22 C6 24 8 26 10 26 C12 26 22 26 22 26"
        stroke={green}
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      {/* Small arc at top-left of zeta */}
      <path
        d="M4 9 C4 7 5 5 7 5"
        stroke={green}
        strokeWidth="2"
        strokeLinecap="round"
        fill="none"
      />

      {/* "Zero" in dark/white */}
      <text
        x="30"
        y="22"
        fontFamily="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
        fontSize="16"
        fontWeight="700"
        fill={textColor}
        letterSpacing="-0.3"
      >
        Zero
      </text>

      {/* "Zeta" in green */}
      <text
        x="78"
        y="22"
        fontFamily="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
        fontSize="16"
        fontWeight="700"
        fill={green}
        letterSpacing="-0.3"
      >
        Zeta
      </text>
    </svg>
  )
}
