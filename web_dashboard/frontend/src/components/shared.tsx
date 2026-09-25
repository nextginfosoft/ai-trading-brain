import clsx from 'clsx'
import { CalendarClock, Check, Clock3, TriangleAlert } from 'lucide-react'
import type { Decision, OpenPosition, Scheduler } from '../lib/api'
import { compactMoney, num, price, time, titleCase } from '../lib/format'
import { Badge, DataTable, EmptyState, directionLabel, directionTone, type Column } from './ui'

// ── Today's schedule ─────────────────────────────────────────────────────

const SLOT_STYLE = {
  DONE: { icon: Check, cls: 'text-profit', label: 'Done' },
  MISSED: { icon: TriangleAlert, cls: 'text-warn', label: 'Missed' },
  PENDING: { icon: Clock3, cls: 'text-ink-3', label: 'Pending' },
  WEEKEND_ONLY: { icon: CalendarClock, cls: 'text-ink-3', label: 'Weekends' },
  WEEKDAY_ONLY: { icon: CalendarClock, cls: 'text-ink-3', label: 'Weekdays' },
} as const

export function ScheduleList({ scheduler, compact = false }: { scheduler: Scheduler; compact?: boolean }) {
  if (!scheduler.slots.length) return <EmptyState title="No schedule found in config.py" />
  const nextName = scheduler.next?.name
  return (
    <ol className={clsx('space-y-0.5', compact && 'max-h-[340px] overflow-y-auto pr-1')}>
      {scheduler.slots.map((s) => {
        const st = SLOT_STYLE[s.status]
        const Icon = st.icon
        const isNext = s.name === nextName
        return (
          <li
            key={s.name}
            className={clsx(
              'flex items-center gap-3 rounded-lg px-2 py-1.5 text-[13px]',
              isNext && 'bg-accent-soft',
            )}
          >
            <span className="num w-11 shrink-0 text-ink-3">{s.time}</span>
            <span className={clsx('min-w-0 flex-1 truncate', s.status === 'PENDING' ? 'text-ink-2' : 'text-ink')}>
              {s.label}
            </span>
            {isNext ? (
              <Badge tone="accent">Next</Badge>
            ) : (
              <span className={clsx('inline-flex items-center gap-1 text-[11px]', st.cls)}>
                <Icon className="size-3.5" aria-hidden />
                {st.label}
              </span>
            )}
          </li>
        )
      })}
    </ol>
  )
}

// ── Decisions ────────────────────────────────────────────────────────────

export function decisionTone(d: string | null | undefined) {
  const v = (d || '').toUpperCase()
  if (v === 'APPROVED') return 'profit' as const
  if (v === 'REJECTED') return 'loss' as const
  return 'neutral' as const
}

function ScoreBar({ value }: { value: number | null }) {
  if (value == null) return <span className="text-ink-3">—</span>
  const w = Math.max(0, Math.min(1, value / 10)) * 100
  return (
    <span className="inline-flex items-center gap-1.5" title={`${value.toFixed(1)} / 10`}>
      <span className="relative h-1.5 w-10 rounded-full bg-panel-3">
        <span className="absolute inset-y-0 left-0 rounded-full bg-accent" style={{ width: `${w}%` }} />
      </span>
      <span className="text-ink-2">{value.toFixed(1)}</span>
    </span>
  )
}

export function DecisionsTable({
  rows,
  showScores = true,
  maxHeight,
}: {
  rows: Decision[]
  showScores?: boolean
  maxHeight?: number
}) {
  const cols: Column<Decision>[] = [
    { key: 'ts', header: 'Time', render: (r) => <span className="text-ink-3">{time(r.ts)}</span>, sort: (r) => r.ts },
    { key: 'symbol', header: 'Symbol', render: (r) => <span className="font-medium">{r.symbol}</span>, sort: (r) => r.symbol },
    {
      key: 'dir',
      header: 'Side',
      render: (r) => <Badge tone={directionTone(r.direction)}>{directionLabel(r.direction)}</Badge>,
    },
    {
      key: 'strategy',
      header: 'Strategy',
      render: (r) => <span className="text-ink-2">{titleCase(r.strategy)}</span>,
      sort: (r) => r.strategy,
    },
    {
      key: 'conf',
      header: 'Confidence',
      align: 'right',
      render: (r) => num(r.confidence),
      sort: (r) => r.confidence,
    },
    {
      key: 'decision',
      header: 'Decision',
      render: (r) => <Badge tone={decisionTone(r.decision)}>{titleCase(r.decision)}</Badge>,
      sort: (r) => r.decision,
    },
    ...(showScores
      ? ([
          { key: 'tech', header: 'Technical', render: (r) => <ScoreBar value={r.technical_score} />, sort: (r) => r.technical_score },
          { key: 'risk', header: 'Risk', render: (r) => <ScoreBar value={r.risk_score} />, sort: (r) => r.risk_score },
          { key: 'macro', header: 'Macro', render: (r) => <ScoreBar value={r.macro_score} />, sort: (r) => r.macro_score },
          { key: 'sent', header: 'Sentiment', render: (r) => <ScoreBar value={r.sentiment_score} />, sort: (r) => r.sentiment_score },
        ] as Column<Decision>[])
      : []),
    {
      key: 'reason',
      header: 'Rejection reason',
      render: (r) => (
        <span className="block max-w-[320px] truncate text-ink-3" title={r.rejection_reason || ''}>
          {r.rejection_reason || '—'}
        </span>
      ),
    },
  ]
  return (
    <DataTable
      rows={rows}
      columns={cols}
      rowKey={(r) => r.id}
      maxHeight={maxHeight}
      empty={
        <EmptyState
          title="No decisions recorded yet"
          hint="Signals reach the decision stage only after passing StrategyLab, risk checks and simulation."
        />
      }
    />
  )
}

// ── Open positions ───────────────────────────────────────────────────────

export function OpenPositionsTable({ rows }: { rows: OpenPosition[] }) {
  const cols: Column<OpenPosition>[] = [
    { key: 'symbol', header: 'Symbol', render: (r) => <span className="font-medium">{r.symbol}</span>, sort: (r) => r.symbol },
    { key: 'side', header: 'Side', render: (r) => <Badge tone={directionTone(r.direction)}>{directionLabel(r.direction)}</Badge> },
    { key: 'qty', header: 'Qty', align: 'right', render: (r) => r.quantity ?? '—', sort: (r) => r.quantity },
    { key: 'entry', header: 'Entry', align: 'right', render: (r) => price(r.entry_price) },
    { key: 'sl', header: 'Stop', align: 'right', render: (r) => <span className="text-loss/90">{price(r.stop_loss)}</span> },
    { key: 'tgt', header: 'Target', align: 'right', render: (r) => <span className="text-profit/90">{price(r.target)}</span> },
    {
      key: 'risk',
      header: 'Risk / reward',
      align: 'right',
      render: (r) => {
        if (r.entry_price == null || r.stop_loss == null || r.target == null) return '—'
        const risk = Math.abs(r.entry_price - r.stop_loss)
        return risk ? `1 : ${(Math.abs(r.target - r.entry_price) / risk).toFixed(1)}` : '—'
      },
    },
    { key: 'exp', header: 'Exposure', align: 'right', render: (r) => compactMoney(r.exposure), sort: (r) => r.exposure },
    { key: 'strategy', header: 'Strategy', render: (r) => <span className="text-ink-2">{titleCase(r.strategy)}</span> },
    { key: 'opened', header: 'Opened', render: (r) => <span className="text-ink-3">{time(r.opened_at)}</span>, sort: (r) => r.opened_at },
  ]
  return (
    <DataTable
      rows={rows}
      columns={cols}
      rowKey={(r) => r.order_id}
      initialSort={{ key: 'opened', dir: 'desc' }}
      empty={<EmptyState title="No open positions" hint="Approved trades appear here until they hit stop, target or square-off." />}
    />
  )
}
