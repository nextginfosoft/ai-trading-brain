import clsx from 'clsx'

/**
 * TradeSense AI mark: a rising price line ending in a signal node, with two
 * "sensing" arcs radiating from it. Drawn on a 32-unit grid so it stays crisp
 * down to favicon size (public/favicon.svg is the same drawing on a tile).
 */
export function LogoMark({ size = 32, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      className={className}
      role="img"
      aria-label="TradeSense AI logo"
    >
      <rect width="32" height="32" rx="8" fill="#12151a" />
      <rect x="0.5" y="0.5" width="31" height="31" rx="7.5" stroke="rgb(255 255 255 / 0.08)" />
      <path d="M6 23 L11.5 17 L15.5 20 L21 13" stroke="#3987e5" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M24.2 9.8 a4.5 4.5 0 0 1 0 6.4" stroke="#6da7ec" strokeWidth="1.7" strokeLinecap="round" />
      <path d="M26.6 7.4 a7.9 7.9 0 0 1 0 11.2" stroke="#6da7ec" strokeOpacity="0.5" strokeWidth="1.7" strokeLinecap="round" />
      <circle cx="21" cy="13" r="3" fill="#1fb85a" stroke="#12151a" strokeWidth="1.5" />
    </svg>
  )
}

export function Wordmark({ className, subtitle }: { className?: string; subtitle?: string }) {
  return (
    <div className={clsx('leading-tight', className)}>
      <div className="flex items-center gap-1.5 text-[14px] font-semibold tracking-tight">
        TradeSense
        <span className="rounded-[5px] bg-accent-soft px-1 py-px text-[10px] font-semibold tracking-wide text-[#8dbdf3]">
          AI
        </span>
      </div>
      {subtitle && <div className="text-[11px] text-ink-3">{subtitle}</div>}
    </div>
  )
}
