import { Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { ChartCard, EquityChart, HBars, Legend, PnlBars, CHART_COLORS } from '../components/charts'
import { OpenPositionsTable } from '../components/shared'
import { Badge, Card, DataTable, EmptyState, Pnl, QueryState, Segmented, StatTile, directionLabel, directionTone } from '../components/ui'
import { useTrades, type ClosedTrade } from '../lib/api'
import { compactMoney, money, pct, price, shortDate, signedMoney, time, titleCase } from '../lib/format'

type Outcome = 'all' | 'win' | 'loss'

export default function TradesPage() {
  const { data, isLoading, error } = useTrades()
  const [outcome, setOutcome] = useState<Outcome>('all')
  const [strategy, setStrategy] = useState('')
  const [query, setQuery] = useState('')

  const filtered = useMemo(() => {
    if (!data) return []
    const q = query.trim().toUpperCase()
    return data.closed_trades.filter(
      (t) =>
        (outcome === 'all' || (outcome === 'win' ? t.pnl > 0 : t.pnl < 0)) &&
        (!strategy || t.strategy === strategy) &&
        (!q || t.symbol?.toUpperCase().includes(q)),
    )
  }, [data, outcome, strategy, query])

  const exitReasons = useMemo(() => {
    const counts = new Map<string, number>()
    for (const t of data?.closed_trades ?? []) {
      const k = titleCase(t.reason || 'unknown')
      counts.set(k, (counts.get(k) ?? 0) + 1)
    }
    return [...counts].map(([label, value]) => ({ label, value })).sort((a, b) => b.value - a.value)
  }, [data])

  if (!data) return <QueryState isLoading={isLoading} error={error} />
  const { stats } = data
  const pf = stats.profit_factor

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatTile
          label="Net P&L"
          value={signedMoney(stats.total_pnl)}
          tone={stats.total_pnl > 0 ? 'profit' : stats.total_pnl < 0 ? 'loss' : 'neutral'}
          hint={`on ${compactMoney(data.capital)} capital`}
        />
        <StatTile label="Closed trades" value={stats.total_trades} hint={`${stats.open_count} still open`} />
        <StatTile label="Win rate" value={pct(stats.win_rate, 0)} hint="Target ≥ 50%" />
        <StatTile label="Profit factor" value={pf != null ? pf.toFixed(2) : '—'} hint="Gross wins ÷ gross losses" />
        <StatTile
          label="Avg win / loss"
          value={
            <span className="text-base">
              <span className="text-profit">{stats.avg_win != null ? compactMoney(stats.avg_win) : '—'}</span>
              <span className="text-ink-3"> / </span>
              <span className="text-loss">{stats.avg_loss != null ? compactMoney(stats.avg_loss) : '—'}</span>
            </span>
          }
        />
        <StatTile
          label="Max drawdown"
          value={stats.max_drawdown ? `−${compactMoney(stats.max_drawdown)}` : '₹0'}
          tone={stats.max_drawdown ? 'loss' : 'neutral'}
          hint={data.capital ? `${((stats.max_drawdown / data.capital) * 100).toFixed(2)}% of capital · limit 15%` : undefined}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <ChartCard
          title="Equity curve"
          subtitle="Cumulative realised P&L"
          chart={<EquityChart points={data.equity_curve} height={240} />}
          table={
            <DataTable
              rows={[...data.equity_curve].reverse()}
              rowKey={(r, i) => `${r.ts}-${i}`}
              maxHeight={240}
              columns={[
                { key: 'ts', header: 'Closed', render: (r) => time(r.ts) },
                { key: 'pnl', header: 'Trade P&L', align: 'right', render: (r) => <Pnl value={r.pnl} /> },
                { key: 'cum', header: 'Cumulative', align: 'right', render: (r) => signedMoney(r.cumulative) },
              ]}
            />
          }
        />
        <ChartCard
          title="Daily P&L"
          subtitle="Realised per trading day"
          actions={
            <Legend
              items={[
                { label: 'Profit', color: CHART_COLORS.up },
                { label: 'Loss', color: CHART_COLORS.down },
              ]}
            />
          }
          chart={
            <PnlBars
              height={240}
              data={data.by_day.slice(-30).map((d) => ({
                label: shortDate(d.date),
                value: d.pnl,
                sub: `${d.trades} (${d.wins} won)`,
              }))}
            />
          }
          table={
            <DataTable
              rows={[...data.by_day].reverse()}
              rowKey={(r) => r.date}
              maxHeight={240}
              columns={[
                { key: 'date', header: 'Date', render: (r) => shortDate(r.date) },
                { key: 'trades', header: 'Trades', align: 'right', render: (r) => r.trades },
                { key: 'wins', header: 'Wins', align: 'right', render: (r) => r.wins },
                { key: 'pnl', header: 'P&L', align: 'right', render: (r) => <Pnl value={r.pnl} /> },
              ]}
            />
          }
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <ChartCard
          className="xl:col-span-2"
          title="P&L by strategy"
          actions={
            <Legend
              items={[
                { label: 'Profit', color: CHART_COLORS.up },
                { label: 'Loss', color: CHART_COLORS.down },
              ]}
            />
          }
          chart={
            <PnlBars
              height={240}
              data={data.by_strategy.map((s) => ({
                label: titleCase(s.strategy),
                value: s.pnl,
                sub: `${s.trades} · ${pct(s.win_rate, 0)} won`,
              }))}
            />
          }
          table={<StrategyTable rows={data.by_strategy} />}
        />
        <ChartCard
          title="How trades exit"
          subtitle="Closed trades by exit reason"
          chart={<HBars data={exitReasons} valueLabel="Trades" labelWidth={120} />}
          table={
            <DataTable
              rows={exitReasons}
              rowKey={(r) => r.label}
              columns={[
                { key: 'r', header: 'Exit reason', render: (r) => r.label },
                { key: 'c', header: 'Trades', align: 'right', render: (r) => r.value },
              ]}
            />
          }
        />
      </div>

      <Card title="Open positions" subtitle={`${data.open_positions.length} open`} bodyClassName="p-0">
        <OpenPositionsTable rows={data.open_positions} />
      </Card>

      <Card
        title="Closed trades"
        subtitle={`${filtered.length} of ${data.closed_trades.length}`}
        bodyClassName="p-0"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <label className="relative">
              <span className="sr-only">Search symbol</span>
              <Search className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-ink-3" aria-hidden />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Symbol"
                className="h-7 w-28 rounded-lg border border-line bg-panel-2 pr-2 pl-7 text-xs outline-none placeholder:text-ink-3 focus:border-accent"
              />
            </label>
            <label>
              <span className="sr-only">Strategy</span>
              <select
                value={strategy}
                onChange={(e) => setStrategy(e.target.value)}
                className="h-7 rounded-lg border border-line bg-panel-2 px-2 text-xs text-ink-2 outline-none focus:border-accent"
              >
                <option value="">All strategies</option>
                {data.by_strategy.map((s) => (
                  <option key={s.strategy} value={s.strategy}>
                    {titleCase(s.strategy)}
                  </option>
                ))}
              </select>
            </label>
            <Segmented
              label="Outcome"
              value={outcome}
              onChange={setOutcome}
              options={[
                { value: 'all', label: 'All' },
                { value: 'win', label: 'Winners' },
                { value: 'loss', label: 'Losers' },
              ]}
            />
          </div>
        }
      >
        <ClosedTradesTable rows={filtered} />
      </Card>
    </div>
  )
}

function StrategyTable({ rows }: { rows: { strategy: string; trades: number; wins: number; pnl: number; win_rate: number }[] }) {
  return (
    <DataTable
      rows={rows}
      rowKey={(r) => r.strategy}
      maxHeight={280}
      initialSort={{ key: 'pnl', dir: 'desc' }}
      empty={<EmptyState title="No closed trades yet" />}
      columns={[
        { key: 'strategy', header: 'Strategy', render: (r) => titleCase(r.strategy), sort: (r) => r.strategy },
        { key: 'trades', header: 'Trades', align: 'right', render: (r) => r.trades, sort: (r) => r.trades },
        { key: 'wr', header: 'Win rate', align: 'right', render: (r) => pct(r.win_rate, 0), sort: (r) => r.win_rate },
        { key: 'pnl', header: 'P&L', align: 'right', render: (r) => <Pnl value={r.pnl} />, sort: (r) => r.pnl },
      ]}
    />
  )
}

function ClosedTradesTable({ rows }: { rows: ClosedTrade[] }) {
  return (
    <DataTable
      rows={rows}
      rowKey={(r, i) => `${r.order_id}-${i}`}
      maxHeight={520}
      initialSort={{ key: 'closed', dir: 'desc' }}
      empty={<EmptyState title="No closed trades match" hint="Closed paper trades are read from data/paper_trades.csv." />}
      columns={[
        { key: 'closed', header: 'Closed', render: (r) => <span className="text-ink-3">{time(r.closed_at)}</span>, sort: (r) => r.closed_at },
        { key: 'symbol', header: 'Symbol', render: (r) => <span className="font-medium">{r.symbol}</span>, sort: (r) => r.symbol },
        { key: 'side', header: 'Side', render: (r) => <Badge tone={directionTone(r.direction)}>{directionLabel(r.direction)}</Badge> },
        { key: 'qty', header: 'Qty', align: 'right', render: (r) => r.quantity ?? '—' },
        { key: 'entry', header: 'Entry', align: 'right', render: (r) => price(r.entry_price) },
        { key: 'exit', header: 'Exit', align: 'right', render: (r) => price(r.exit_price) },
        { key: 'pnl', header: 'P&L', align: 'right', render: (r) => <Pnl value={r.pnl} />, sort: (r) => r.pnl },
        {
          key: 'ret',
          header: 'Return',
          align: 'right',
          render: (r) => {
            const cost = (r.entry_price ?? 0) * (r.quantity ?? 0)
            return cost ? <span className={r.pnl >= 0 ? 'text-profit' : 'text-loss'}>{pct(r.pnl / cost, 2)}</span> : '—'
          },
          sort: (r) => {
            const cost = (r.entry_price ?? 0) * (r.quantity ?? 0)
            return cost ? r.pnl / cost : null
          },
        },
        { key: 'strategy', header: 'Strategy', render: (r) => <span className="text-ink-2">{titleCase(r.strategy)}</span>, sort: (r) => r.strategy },
        {
          key: 'reason',
          header: 'Exit reason',
          render: (r) => (
            <span className="block max-w-[220px] truncate text-ink-3" title={r.reason}>
              {titleCase(r.reason)}
            </span>
          ),
        },
        { key: 'opened', header: 'Opened', render: (r) => <span className="text-ink-3">{time(r.opened_at)}</span> },
        { key: 'value', header: 'Value', align: 'right', render: (r) => money((r.entry_price ?? 0) * (r.quantity ?? 0)) },
      ]}
    />
  )
}
