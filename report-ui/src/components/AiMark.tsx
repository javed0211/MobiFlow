import type { SVGProps } from 'react'

/** Rounded square mark with "AI" — used in sidebar and AI Insights. */
export function AiMark({ size = 15, className, ...rest }: SVGProps<SVGSVGElement> & { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
      {...rest}
    >
      <rect x="1.25" y="1.25" width="13.5" height="13.5" rx="3.5" stroke="currentColor" strokeWidth="1.25" fill="none" />
      <text
        x="8"
        y="11"
        textAnchor="middle"
        fill="currentColor"
        fontSize="6.5"
        fontWeight="700"
        fontFamily="Montserrat, Arial, sans-serif"
      >
        AI
      </text>
    </svg>
  )
}
