import clsx from 'clsx'
import { Pause, Play } from 'lucide-react'
import { useMemo, useState } from 'react'
import { ChartCard, DurationBars } from '../components/charts'
import { ScheduleList } from '../components/shared'
import { Badge, Card, DataTable, EmptyState, QueryState, StatTile, type Tone } from '../components/ui'
import { useEod, useHealth, type TelemetryEvent } from '../lib/api'
import { time, titleCase } from '../lib/format'

const SERVICE_TONE: Record<string, Tone> = { ONLINE: 'profit', IDLE: 'warn', OFFLINE: 'loss', UNKNOWN: 'neutral' }

function eventTone(type: string): Tone {
  const t = type.toLowerCase()
  if (t.includes('error') || t.includes('fail') || t.includes('kill')) return 'loss'
  if (t.includes('warn') || t.includes('degrad') || t.includes('reject')) return 'warn'
  if (t.includes('order') || t.includes('approved') || t.includes('executed')) return 'profit'
  if (t.includes('cycle')) return 'accent'
  return 'neutral'
}

function payloadSummary(p: TelemetryEvent['payload']): string {
  if (typeof p === 'string') return p
  return Object.entries(p ?? {})
    .slice(0, 6)
    .map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
    .join('  ')
}

export default function HealthPage() {
  const { data, isLoading, error } = useHealth()
  const eod = useEod()
  const [paused, setPaused] = useState(false)
  const [frozen, setFrozen] = useState<TelemetryEvent[] | null>(null)
  const [agentFilter, setAgentFilter] = useState('')

  const events = useMemo(() => {
    const src = paused && frozen ? frozen : (data?.events ?? [])
    return agentFilter ? src.filter((e) => e.source_agent === agentFilter) : src
  }, [data, paused, frozen, agentFilter])

  if (!data) return <QueryState isLoading={isLoading} error={error} />

  const cycles = [...data.cycles].reverse()
  const completed = data.cycles.filter((c) => c.cycle_ms > 0)
  const avgMs = completed.length ? completed.reduce((a, c) => a + c.cycle_ms, 0) / completed.length : null
  const errors = data.cycles.filter((c) => c.had_error).length
  const agentErrors = data.agents.reduce((a, g) => a + (g.error_count || 0), 0)

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          label="Trading engine"
          value={<Badge tone={SERVICE_TONE[data.service.status] ?? 'neutral'} dot>{data.service.status}</Badge>}
          hint={data.service.age_min != null ? `Last event ${data.service.age_min} min ago` : 'No events yet'}
        />
        <StatTile label="Avg cycle time" value={avgMs ? `${(avgMs / 1000).toFixed(1)}s` : '—'} hint={`Over ${completed.length} cycles`} />
        <StatTile label="Cycles with errors" value={errors} tone={errors ? 'loss' : 'neutral'} hint={`Of last ${data.cycles.length}`} />
        <StatTile label="Agent error events" value={agentErrors} tone={agentErrors ? 'loss' : 'neutral'} hint={`${data.agents.length} agents reporting`} />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <ChartCard
          className="xl:col-span-2"
          title="Cycle duration"
          subtitle="Last 50 cycles"
          chart={<DurationBars data={cycles.map((c) => ({ label: time(c.started_at), value: c.cycle_ms || 0 }))} />}
          table={
            <DataTable
              rows={data.cycles}
              rowKey={(r) => r.cycle_id}
              maxHeight={220}
              columns={[
                { key: 't', header: 'Started', render: (r) => time(r.started_at) },
                { key: 'ms', header: 'Duration', align: 'right', render: (r) => (r.cycle_ms ? `${(r.cycle_ms / 1000).toFixed(1)}s` : '—') },
                { key: 'reg', header: 'Regime', render: (r) => titleCase(r.regime) },
                { key: 'sig', header: 'Signals', align: 'right', render: (r) => r.signals_generated },
                { key: 'ex', header: 'Executed', align: 'right', render: (r) => r.trades_executed },
                {
                  key: 'st',
                  header: 'Status',
                  render: (r) => (r.had_error ? <Badge tone="loss">Error</Badge> : <Badge>OK</Badge>),
                },
              ]}
            />
          }
        />
        <Card title="Today's schedule" subtitle="IST">
          <ScheduleList scheduler={data.scheduler} compact />
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-5">
        <Card title="Agent health" subtitle="Click an agent to filter the event stream" bodyClassName="p-0" className="xl:col-span-2">
          <DataTable
            rows={data.agents}
            rowKey={(r) => r.agent}
            maxHeight={460}
            initialSort={{ key: 'events', dir: 'desc' }}
            columns={[
              {
                key: 'agent',
                header: 'Agent',
                sort: (r) => r.agent,
                render: (r) => (
                  <button
                    onClick={() => setAgentFilter(agentFilter === r.agent ? '' : r.agent)}
                    className={clsx('max-w-[200px] truncate text-left hover:text-accent', agentFilter === r.agent && 'text-accent')}
                  >
                    {r.agent}
                  </button>
                ),
              },
              { key: 'events', header: 'Events', align: 'right', render: (r) => r.event_count, sort: (r) => r.event_count },
              {
                key: 'err',
                header: 'Errors',
                align: 'right',
                sort: (r) => r.error_count,
                render: (r) => (r.error_count ? <span className="text-loss">{r.error_count}</span> : <span className="text-ink-3">0</span>),
              },
              { key: 'seen', header: 'Last seen', render: (r) => <span className="text-ink-3">{time(r.last_seen)}</span>, sort: (r) => r.last_seen },
            ]}
          />
        </Card>

        <Card
          className="xl:col-span-3"
          title="Live event stream"
          subtitle={agentFilter ? `Filtered: ${agentFilter}` : `Latest ${events.length} events`}
          bodyClassName="p-0"
          actions={
            <>
              {agentFilter && (
                <button onClick={() => setAgentFilter('')} className="text-xs text-accent hover:underline">
                  Clear filter
                </button>
              )}
              <button
                onClick={() => {
                  setFrozen(paused ? null : (data.events ?? []))
                  setPaused(!paused)
                }}
                className="inline-flex items-center gap-1 rounded-md border border-line px-2 py-1 text-xs text-ink-2 hover:bg-panel-3"
              >
                {paused ? <Play className="size-3" aria-hidden /> : <Pause className="size-3" aria-hidden />}
                {paused ? 'Resume' : 'Pause'}
              </button>
            </>
          }
        >
          {events.length ? (
            <ol className="max-h-[460px] divide-y divide-line overflow-y-auto font-mono text-[12px]">
              {events.map((e) => (
                <li key={e.id} className="grid grid-cols-[64px_minmax(0,190px)_1fr] items-start gap-3 px-4 py-1.5 hover:bg-panel-2/60">
                  <span className="text-ink-3">{time(e.ts).slice(-8)}</span>
                  <span className="truncate" title={e.event_type}>
                    <Badge tone={eventTone(e.event_type)}>{e.event_type}</Badge>
                  </span>
                  <span className="min-w-0 truncate text-ink-3" title={payloadSummary(e.payload)}>
                    <span className="text-ink-2">{e.source_agent}</span> {payloadSummary(e.payload)}
                  </span>
                </li>
              ))}
            </ol>
          ) : (
            <EmptyState title="No events yet" />
          )}
        </Card>
      </div>

      <Card title="End-of-day report" subtitle="Written by the orchestrator at 15:35 IST">
        {eod.data?.report_text ? (
          <pre className="max-h-[420px] overflow-auto rounded-lg bg-panel-2 p-4 font-mono text-[12px] leading-relaxed whitespace-pre-wrap text-ink-2">
            {eod.data.report_text}
          </pre>
        ) : eod.data?.daily ? (
          <pre className="max-h-[420px] overflow-auto rounded-lg bg-panel-2 p-4 font-mono text-[12px] text-ink-2">
            {JSON.stringify(eod.data.daily, null, 2)}
          </pre>
        ) : (
          <EmptyState title="No end-of-day report yet" hint="It appears after the first 15:35 learning cycle on a trading day." />
        )}
      </Card>
    </div>
  )
}
