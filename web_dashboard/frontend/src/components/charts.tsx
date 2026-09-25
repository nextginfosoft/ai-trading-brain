import clsx from 'clsx'
import { BarChart3, Table2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { compactMoney, signedMoney } from '../lib/format'
import { Card, EmptyState } from './ui'

// Validated with the dataviz palette validator on the panel surface (#12151a).
const C = {
  up: '#3987e5',
  down: '#e66767',
  grid: '#23272e',
  axis: '#6f767f',
  // Ordinal blue ramp, dark → light (validated --ordinal, all checks pass).
  ordinal: ['#184f95', '#256abf', '#3987e5', '#6da7ec', '#9ec5f4'],
}

const AXIS = { stroke: C.axis, fontSize: 11, tickLine: false, axisLine: false } as const

/** Clean round y-ticks (1/2/2.5/5 × 10ⁿ steps) spanning the data, always including 0. */
export function niceTicks(values: number[], count = 5): { ticks: number[]; domain: [number, number] } {
  const lo = Math.min(0, ...values)
  const hi = Math.max(0, ...values)
  const span = hi - lo || 1
  const raw = span / (count - 1)
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag
  const start = Math.floor(lo / step) * step
  const end = Math.ceil(hi / step) * step
  const ticks: number[] = []
  for (let t = start; t <= end + step / 2; t += step) ticks.push(Math.round(t * 100) / 100)
  return { ticks, domain: [start, end] }
}

/** Card with a chart ⇄ table toggle — every chart has a table-view twin. */
export function ChartCard({
  title,
  subtitle,
  chart,
  table,
  actions,
  className,
}: {
  title: string
  subtitle?: string
  chart: ReactNode
  table: ReactNode
  actions?: ReactNode
  className?: string
}) {
  const [view, setView] = useState<'chart' | 'table'>('chart')
  return (
    <Card
      title={title}
      subtitle={subtitle}
      className={className}
      actions={
        <>
          {actions}
          <button
            onClick={() => setView(view === 'chart' ? 'table' : 'chart')}
            className="rounded-md p-1 text-ink-3 hover:bg-panel-3 hover:text-ink-2"
            aria-label={view === 'chart' ? 'Show as table' : 'Show as chart'}
            title={view === 'chart' ? 'Show as table' : 'Show as chart'}
          >
            {view === 'chart' ? <Table2 className="size-4" /> : <BarChart3 className="size-4" />}
          </button>
        </>
      }
    >
      {view === 'chart' ? chart : table}
    </Card>
  )
}

function TooltipBox({ title, rows }: { title?: ReactNode; rows: { label: string; value: ReactNode; swatch?: string }[] }) {
  return (
    <div className="rounded-lg border border-line-strong bg-panel-2 px-3 py-2 text-xs shadow-xl">
      {title && <div className="mb-1 text-ink-3">{title}</div>}
      {rows.map((r) => (
        <div key={r.label} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5 text-ink-2">
            {r.swatch && <span className="size-2 rounded-full" style={{ background: r.swatch }} aria-hidden />}
            {r.label}
          </span>
          <span className="num font-medium text-ink">{r.value}</span>
        </div>
      ))}
    </div>
  )
}

// ── Equity curve (single series: cumulative realised P&L) ─────────────────

export function EquityChart({ points, height = 260 }: { points: { ts: string; cumulative: number; pnl: number }[]; height?: number }) {
  if (points.length < 2)
    return (
      <EmptyState
        title="Equity curve appears after the first closed trades"
        hint="Each closed paper trade adds a point. Nothing has closed yet."
      />
    )
  const data = [{ ts: 'Start', cumulative: 0, pnl: 0 }, ...points]
  const y = niceTicks(data.map((d) => d.cumulative))
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={C.grid} vertical={false} />
          <XAxis dataKey="ts" {...AXIS} minTickGap={48} tickFormatter={(v: string) => (v === 'Start' ? '' : v.slice(5, 10))} />
          <YAxis {...AXIS} width={64} ticks={y.ticks} domain={y.domain} tickFormatter={(v: number) => compactMoney(v)} />
          <ReferenceLine y={0} stroke="#383d45" />
          <Tooltip
            cursor={{ stroke: '#4a5059', strokeWidth: 1 }}
            content={({ active, payload }) =>
              active && payload?.length ? (
                <TooltipBox
                  title={String(payload[0].payload.ts)}
                  rows={[
                    { label: 'Cumulative P&L', value: signedMoney(payload[0].payload.cumulative), swatch: C.up },
                    { label: 'This trade', value: signedMoney(payload[0].payload.pnl) },
                  ]}
                />
              ) : null
            }
          />
          <Area
            type="monotone"
            dataKey="cumulative"
            stroke={C.up}
            strokeWidth={2}
            fill={C.up}
            fillOpacity={0.1}
            activeDot={{ r: 4, stroke: '#12151a', strokeWidth: 2, fill: C.up }}
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

// ── Diverging P&L bars (profit up / loss down from zero) ──────────────────

export function PnlBars({ data, height = 240 }: { data: { label: string; value: number; sub?: string }[]; height?: number }) {
  if (!data.length) return <EmptyState title="No closed trades yet" />
  const y = niceTicks(data.map((d) => d.value))
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barCategoryGap="20%">
          <CartesianGrid stroke={C.grid} vertical={false} />
          <XAxis dataKey="label" {...AXIS} minTickGap={16} interval={data.length <= 12 ? 0 : 'preserveStartEnd'} />
          <YAxis {...AXIS} width={64} ticks={y.ticks} domain={y.domain} tickFormatter={(v: number) => compactMoney(v)} />
          <ReferenceLine y={0} stroke="#383d45" />
          <Tooltip
            cursor={{ fill: 'rgba(255,255,255,0.03)' }}
            content={({ active, payload }) =>
              active && payload?.length ? (
                <TooltipBox
                  title={payload[0].payload.label}
                  rows={[
                    {
                      label: payload[0].payload.value >= 0 ? 'Profit' : 'Loss',
                      value: signedMoney(payload[0].payload.value),
                      swatch: payload[0].payload.value >= 0 ? C.up : C.down,
                    },
                    ...(payload[0].payload.sub ? [{ label: 'Trades', value: payload[0].payload.sub }] : []),
                  ]}
                />
              ) : null
            }
          />
          <Bar dataKey="value" maxBarSize={24} isAnimationActive={false}>
            {data.map((d) => (
              <Cell key={d.label} fill={d.value >= 0 ? C.up : C.down} radius={(d.value >= 0 ? [4, 4, 0, 0] : [0, 0, 4, 4]) as unknown as number} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

// ── Horizontal single-series bars (counts by category) ────────────────────

export function HBars({
  data,
  valueLabel = 'Count',
  format = (v: number) => v.toLocaleString('en-IN'),
  labelWidth = 150,
}: {
  data: { label: string; value: number }[]
  valueLabel?: string
  format?: (v: number) => string
  labelWidth?: number
}) {
  if (!data.length) return <EmptyState title="Nothing to show yet" />
  const height = data.length * 30 + 16
  const maxChars = Math.floor((labelWidth - 12) / 7) // ~7px per char at 12px; full label stays in tooltip + table
  const fit = (v: string) => (v.length > maxChars ? v.slice(0, maxChars - 1) + '…' : v)
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 48, bottom: 4, left: 0 }} barCategoryGap={8}>
          <XAxis type="number" hide />
          <YAxis
            type="category"
            dataKey="label"
            {...AXIS}
            width={labelWidth}
            tick={{ fill: '#a3a9b1', fontSize: 12 }}
            tickFormatter={fit}
          />
          <Tooltip
            cursor={{ fill: 'rgba(255,255,255,0.03)' }}
            content={({ active, payload }) =>
              active && payload?.length ? (
                <TooltipBox title={payload[0].payload.label} rows={[{ label: valueLabel, value: format(payload[0].payload.value), swatch: C.up }]} />
              ) : null
            }
          />
          <Bar dataKey="value" fill={C.up} radius={[0, 4, 4, 0]} maxBarSize={18} isAnimationActive={false}>
            <LabelList dataKey="value" position="right" formatter={(v) => format(Number(v))} fill="#a3a9b1" fontSize={11} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

// ── Signal funnel (ordinal stages) ────────────────────────────────────────

export function Funnel({ stages }: { stages: { label: string; value: number }[] }) {
  const top = Math.max(stages[0]?.value ?? 0, 1)
  return (
    <ol className="space-y-2.5" aria-label="Signal funnel">
      {stages.map((s, i) => {
        const w = (s.value / top) * 100
        const prev = i > 0 ? stages[i - 1].value : null
        const dropped = prev != null ? prev - s.value : 0
        return (
          <li key={s.label} className="grid grid-cols-[92px_1fr_64px] items-center gap-3">
            <span className="truncate text-xs text-ink-2">{s.label}</span>
            <span className="relative h-5 rounded-[4px] bg-panel-3/60">
              <span
                className="absolute inset-y-0 left-0 rounded-[4px] transition-[width] duration-500"
                style={{ width: `${Math.max(w, s.value ? 2 : 0)}%`, background: C.ordinal[Math.min(i, C.ordinal.length - 1)] }}
              />
            </span>
            <span className="num text-right text-xs">
              <span className="font-medium text-ink">{s.value}</span>
              {dropped > 0 && <span className="ml-1 text-ink-3">−{dropped}</span>}
            </span>
          </li>
        )
      })}
    </ol>
  )
}

// ── Cycle duration columns ────────────────────────────────────────────────

export function DurationBars({ data, slaMs, height = 200 }: { data: { label: string; value: number }[]; slaMs?: number; height?: number }) {
  if (!data.length) return <EmptyState title="No cycles recorded yet" />
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barCategoryGap="20%">
          <CartesianGrid stroke={C.grid} vertical={false} />
          <XAxis dataKey="label" {...AXIS} minTickGap={24} />
          <YAxis {...AXIS} width={48} tickFormatter={(v: number) => `${(v / 1000).toFixed(0)}s`} />
          {slaMs && <ReferenceLine y={slaMs} stroke="#fab219" strokeOpacity={0.6} />}
          <Tooltip
            cursor={{ fill: 'rgba(255,255,255,0.03)' }}
            content={({ active, payload }) =>
              active && payload?.length ? (
                <TooltipBox
                  title={payload[0].payload.label}
                  rows={[{ label: 'Duration', value: `${(payload[0].payload.value / 1000).toFixed(1)}s`, swatch: C.up }]}
                />
              ) : null
            }
          />
          <Bar dataKey="value" fill={C.up} radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div className={clsx('flex flex-wrap items-center gap-3 text-xs text-ink-3')}>
      {items.map((i) => (
        <span key={i.label} className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm" style={{ background: i.color }} aria-hidden />
          {i.label}
        </span>
      ))}
    </div>
  )
}

export const CHART_COLORS = C
