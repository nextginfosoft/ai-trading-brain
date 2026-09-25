import { Link } from 'react-router-dom'
import { ChartCard, EquityChart, Funnel } from '../components/charts'
import { DecisionsTable, OpenPositionsTable, ScheduleList, decisionTone } from '../components/shared'
import { Badge, Card, DataTable, EmptyState, Pnl, QueryState, StatTile, directionLabel, directionTone } from '../components/ui'
import { useOverview } from '../lib/api'
import { compactMoney, money, num, pct, signedMoney, time, titleCase } from '../lib/format'

export default function OverviewPage() {
  const { data, isLoading, error } = useOverview()
  if (!data) return <QueryState isLoading={isLoading} error={error} />

  const { stats, capital, cycle } = data
  const equity = capital + stats.total_pnl
  const ret = capital ? stats.total_pnl / capital : 0
  const funnel = [
    { label: 'Generated', value: cycle.signals_generated ?? 0 },
    { label: 'Strategy ✓', value: cycle.strategies_assigned ?? 0 },
    { label: 'Risk ✓', value: cycle.risk_approved ?? 0 },
    { label: 'Simulation ✓', value: cycle.sim_approved ?? 0 },
    { label: 'Executed', value: cycle.trades_executed ?? 0 },
  ]

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <div className="col-span-2 lg:col-span-1">
          <StatTile
            hero
            label="Total P&L"
            value={signedMoney(stats.total_pnl)}
            tone={stats.total_pnl > 0 ? 'profit' : stats.total_pnl < 0 ? 'loss' : 'neutral'}
            hint={`${ret >= 0 ? '+' : ''}${(ret * 100).toFixed(2)}% on ${compactMoney(capital)}`}
          />
        </div>
        <StatTile
          label="Today's P&L"
          value={signedMoney(stats.realized_today)}
          tone={stats.realized_today > 0 ? 'profit' : stats.realized_today < 0 ? 'loss' : 'neutral'}
          hint="Realised, closed trades"
        />
        <StatTile
          label="Win rate"
          value={pct(stats.win_rate, 0)}
          hint={`${stats.total_trades} closed trade${stats.total_trades === 1 ? '' : 's'}`}
        />
        <StatTile
          label="Open positions"
          value={stats.open_count}
          hint={stats.open_count ? `${compactMoney(stats.open_exposure)} deployed` : 'Fully in cash'}
        />
        <StatTile label="Account equity" value={money(equity)} hint={`Capital ${money(capital)}`} />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <ChartCard
          className="xl:col-span-2"
          title="Equity curve"
          subtitle="Cumulative realised P&L, paper account"
          chart={<EquityChart points={data.equity_curve} />}
          table={
            <DataTable
              rows={[...data.equity_curve].reverse()}
              rowKey={(r, i) => `${r.ts}-${i}`}
              maxHeight={260}
              columns={[
                { key: 'ts', header: 'Closed', render: (r) => time(r.ts) },
                { key: 'pnl', header: 'Trade P&L', align: 'right', render: (r) => <Pnl value={r.pnl} /> },
                { key: 'cum', header: 'Cumulative', align: 'right', render: (r) => signedMoney(r.cumulative) },
                { key: 'eq', header: 'Equity', align: 'right', render: (r) => money(r.equity) },
              ]}
            />
          }
        />

        <Card
          title="Latest cycle"
          subtitle={cycle.started_at ? `Started ${time(cycle.started_at)}` : 'No cycle has run yet'}
          actions={
            cycle.status && (
              <Badge tone={cycle.status === 'ERROR' ? 'loss' : cycle.status === 'RUNNING' ? 'warn' : 'neutral'} dot>
                {titleCase(cycle.status.toLowerCase())}
              </Badge>
            )
          }
        >
          <dl className="mb-4 grid grid-cols-4 gap-2">
            {[
              ['Regime', titleCase(cycle.regime)],
              ['VIX', num(cycle.vix, 2)],
              ['PCR', num(cycle.pcr, 2)],
              ['Breadth', cycle.breadth != null ? num(cycle.breadth, 2) : '—'],
            ].map(([k, v]) => (
              <div key={k} className="rounded-lg bg-panel-2 px-2.5 py-2">
                <dt className="text-[11px] text-ink-3">{k}</dt>
                <dd className="num mt-0.5 truncate text-[13px] font-medium" title={v}>
                  {v}
                </dd>
              </div>
            ))}
          </dl>
          <div className="mb-2 text-xs text-ink-3">Signal funnel</div>
          <Funnel stages={funnel} />
          {cycle.cycle_ms ? (
            <div className="mt-3 text-[11px] text-ink-3">Cycle took {(cycle.cycle_ms / 1000).toFixed(1)}s</div>
          ) : null}
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card
          className="xl:col-span-2"
          title="Open positions"
          subtitle={`${data.open_positions.length} open`}
          bodyClassName="p-0"
          actions={
            <Link to="/trades" className="text-xs text-accent hover:underline">
              All trades
            </Link>
          }
        >
          <OpenPositionsTable rows={data.open_positions} />
        </Card>

        <Card title="Today's schedule" subtitle="IST, from config.py">
          <ScheduleList scheduler={data.scheduler} compact />
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="Latest approved trade">
          {data.latest_approved ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="text-lg font-semibold">{data.latest_approved.symbol}</div>
                <Badge tone={directionTone(data.latest_approved.direction)}>
                  {directionLabel(data.latest_approved.direction)}
                </Badge>
              </div>
              <dl className="grid grid-cols-2 gap-2 text-[13px]">
                {[
                  ['Strategy', titleCase(data.latest_approved.strategy)],
                  ['Confidence', num(data.latest_approved.confidence)],
                  ['Size modifier', num(data.latest_approved.position_modifier, 2)],
                  ['Time', time(data.latest_approved.ts)],
                ].map(([k, v]) => (
                  <div key={k}>
                    <dt className="text-[11px] text-ink-3">{k}</dt>
                    <dd className="num truncate">{v}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ) : (
            <EmptyState title="No approved trade yet" hint="Trades need a debate score of at least 6.5 to be approved." />
          )}
        </Card>
        <Card
          className="xl:col-span-2"
          title="Recent decisions"
          bodyClassName="p-0"
          actions={
            <Link to="/signals" className="text-xs text-accent hover:underline">
              All signals
            </Link>
          }
        >
          <DecisionsTable rows={data.recent_decisions} showScores={false} maxHeight={320} />
        </Card>
      </div>
      <p className="text-center text-[11px] text-ink-3">
        {data.today_events} telemetry events today · Last engine event {time(data.service.last_ts)}{' '}
        <Badge tone={decisionTone('')}>{data.service.last_event || '—'}</Badge>
      </p>
    </div>
  )
}
