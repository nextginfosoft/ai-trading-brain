import clsx from 'clsx'
import { ArrowDownRight, ArrowUpRight, ChevronDown, ChevronUp, Inbox } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { signedMoney } from '../lib/format'

export function Card({
  title,
  subtitle,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}) {
  return (
    <section className={clsx('rounded-xl border border-line bg-panel', className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          <div className="min-w-0">
            {title && <h2 className="truncate text-[13px] font-medium text-ink">{title}</h2>}
            {subtitle && <p className="truncate text-xs text-ink-3">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={clsx('p-4', bodyClassName)}>{children}</div>
    </section>
  )
}

export function StatTile({
  label,
  value,
  hint,
  tone = 'neutral',
  hero = false,
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  tone?: 'neutral' | 'profit' | 'loss'
  hero?: boolean
}) {
  return (
    <div className="rounded-xl border border-line bg-panel px-4 py-3.5">
      <div className="text-xs text-ink-3">{label}</div>
      <div
        className={clsx(
          'mt-1 font-semibold tracking-tight',
          hero ? 'text-[28px] leading-9' : 'text-xl leading-7',
          tone === 'profit' && 'text-profit',
          tone === 'loss' && 'text-loss',
        )}
      >
        {value}
      </div>
      {hint && <div className="mt-0.5 truncate text-xs text-ink-3">{hint}</div>}
    </div>
  )
}

export function Pnl({ value, className }: { value: number | null | undefined; className?: string }) {
  if (value == null) return <span className={clsx('text-ink-3', className)}>—</span>
  const up = value > 0
  const down = value < 0
  return (
    <span
      className={clsx(
        'num inline-flex items-center gap-0.5 whitespace-nowrap',
        up && 'text-profit',
        down && 'text-loss',
        !up && !down && 'text-ink-2',
        className,
      )}
    >
      {up && <ArrowUpRight className="size-3.5" aria-hidden />}
      {down && <ArrowDownRight className="size-3.5" aria-hidden />}
      {signedMoney(value)}
    </span>
  )
}

const BADGE_TONES = {
  neutral: 'bg-panel-3 text-ink-2',
  accent: 'bg-accent-soft text-[#8dbdf3]',
  profit: 'bg-profit-soft text-profit',
  loss: 'bg-loss-soft text-loss',
  warn: 'bg-warn-soft text-warn',
} as const

export type Tone = keyof typeof BADGE_TONES

export function Badge({ tone = 'neutral', children, dot }: { tone?: Tone; children: ReactNode; dot?: boolean }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-md px-1.5 py-0.5 text-[11px] font-medium whitespace-nowrap',
        BADGE_TONES[tone],
      )}
    >
      {dot && <span className="size-1.5 rounded-full bg-current" aria-hidden />}
      {children}
    </span>
  )
}

export function directionTone(direction: string | null | undefined): Tone {
  const d = (direction || '').toUpperCase()
  if (d.includes('BUY') || d.includes('LONG')) return 'profit'
  if (d.includes('SELL') || d.includes('SHORT')) return 'loss'
  return 'neutral'
}

export function directionLabel(direction: string | null | undefined): string {
  const d = (direction || '').toUpperCase().replace('SIGNALDIRECTION.', '')
  return d || '—'
}

export function EmptyState({ title, hint, icon }: { title: string; hint?: string; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
      <div className="text-ink-3">{icon ?? <Inbox className="size-6" aria-hidden />}</div>
      <div className="text-sm text-ink-2">{title}</div>
      {hint && <div className="max-w-sm text-xs text-ink-3">{hint}</div>}
    </div>
  )
}

export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
}: {
  value: T
  onChange: (v: T) => void
  options: { value: T; label: string }[]
  label: string
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-lg border border-line bg-panel-2 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={clsx(
            'rounded-md px-2.5 py-1 text-xs transition-colors',
            value === o.value ? 'bg-panel-3 text-ink' : 'text-ink-3 hover:text-ink-2',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export type Column<T> = {
  key: string
  header: string
  render: (row: T) => ReactNode
  sort?: (row: T) => number | string | null | undefined
  align?: 'left' | 'right'
  className?: string
}

export function DataTable<T>({
  rows,
  columns,
  rowKey,
  empty,
  maxHeight,
  initialSort,
}: {
  rows: T[]
  columns: Column<T>[]
  rowKey: (row: T, i: number) => string | number
  empty?: ReactNode
  maxHeight?: number
  initialSort?: { key: string; dir: 'asc' | 'desc' }
}) {
  const [sort, setSort] = useState(initialSort)
  const sorted = useMemo(() => {
    const col = columns.find((c) => c.key === sort?.key)
    if (!sort || !col?.sort) return rows
    const get = col.sort
    return [...rows].sort((a, b) => {
      const va = get(a)
      const vb = get(b)
      if (va == null) return 1
      if (vb == null) return -1
      const cmp = va < vb ? -1 : va > vb ? 1 : 0
      return sort.dir === 'asc' ? cmp : -cmp
    })
  }, [rows, columns, sort])

  if (!rows.length) return <>{empty ?? <EmptyState title="No data yet" />}</>

  return (
    <div className="overflow-auto" style={maxHeight ? { maxHeight } : undefined}>
      <table className="w-full border-collapse text-[13px]">
        <thead className="sticky top-0 z-10 bg-panel">
          <tr>
            {columns.map((c) => {
              const active = sort?.key === c.key
              return (
                <th
                  key={c.key}
                  scope="col"
                  className={clsx(
                    'border-b border-line px-3 py-2 text-[11px] font-medium whitespace-nowrap text-ink-3',
                    c.align === 'right' ? 'text-right' : 'text-left',
                  )}
                  aria-sort={active ? (sort!.dir === 'asc' ? 'ascending' : 'descending') : undefined}
                >
                  {c.sort ? (
                    <button
                      className={clsx('inline-flex items-center gap-0.5 hover:text-ink-2', active && 'text-ink-2')}
                      onClick={() =>
                        setSort(
                          active && sort!.dir === 'desc' ? { key: c.key, dir: 'asc' } : { key: c.key, dir: 'desc' },
                        )
                      }
                    >
                      {c.header}
                      {active &&
                        (sort!.dir === 'asc' ? (
                          <ChevronUp className="size-3" aria-hidden />
                        ) : (
                          <ChevronDown className="size-3" aria-hidden />
                        ))}
                    </button>
                  ) : (
                    c.header
                  )}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr key={rowKey(row, i)} className="border-b border-line last:border-0 hover:bg-panel-2/60">
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={clsx(
                    'num px-3 py-2 whitespace-nowrap',
                    c.align === 'right' ? 'text-right' : 'text-left',
                    c.className,
                  )}
                >
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function QueryState({ isLoading, error }: { isLoading: boolean; error: unknown }) {
  if (isLoading)
    return <div className="py-16 text-center text-sm text-ink-3">Loading…</div>
  if (error)
    return (
      <EmptyState
        title="Can't reach the dashboard API"
        hint={`${error instanceof Error ? error.message : String(error)} — is web_dashboard.server running?`}
      />
    )
  return null
}
