import { Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { ChartCard, Funnel, HBars } from '../components/charts'
import { DecisionsTable } from '../components/shared'
import { Card, DataTable, QueryState, Segmented, StatTile } from '../components/ui'
import { useDecisions } from '../lib/api'
import { num, pct, time, titleCase } from '../lib/format'

type Filter = '' | 'APPROVED' | 'REJECTED'

export default function SignalsPage() {
  const [filter, setFilter] = useState<Filter>('')
  const [query, setQuery] = useState('')
  const { data, isLoading, error, isPlaceholderData } = useDecisions(filter)

  const rows = useMemo(() => {
    const q = query.trim().toUpperCase()
    return (data?.decisions ?? []).filter((d) => !q || d.symbol?.toUpperCase().includes(q))
  }, [data, query])

  if (!data) return <QueryState isLoading={isLoading} error={error} />

  const hist = data.funnel_history
  const sum = (k: keyof (typeof hist)[number]) => hist.reduce((a, c) => a + (Number(c[k]) || 0), 0)
  const totals = {
    generated: sum('signals_generated'),
    strategy: sum('strategies_assigned'),
    risk: sum('risk_approved'),
    sim: sum('sim_approved'),
    executed: sum('trades_executed'),
  }
  const approved = data.strategies.reduce((a, s) => a + (s.approved || 0), 0)
  const decided = data.strategies.reduce((a, s) => a + s.count, 0)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Segmented
          label="Decision filter"
          value={filter}
          onChange={setFilter}
          options={[
            { value: '', label: 'All decisions' },
            { value: 'APPROVED', label: 'Approved' },
            { value: 'REJECTED', label: 'Rejected' },
          ]}
        />
        <label className="relative">
          <span className="sr-only">Search symbol</span>
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-ink-3" aria-hidden />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search symbol"
            className="h-8 w-44 rounded-lg border border-line bg-panel pr-2 pl-8 text-xs outline-none placeholder:text-ink-3 focus:border-accent"
          />
        </label>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Signals generated" value={totals.generated.toLocaleString('en-IN')} hint={`Last ${hist.length} cycles`} />
        <StatTile
          label="Reached execution"
          value={totals.executed.toLocaleString('en-IN')}
          hint={totals.generated ? `${pct(totals.executed / totals.generated, 1)} of generated` : undefined}
        />
        <StatTile label="Debate decisions" value={decided.toLocaleString('en-IN')} hint="All time" />
        <StatTile label="Approval rate" value={decided ? pct(approved / decided, 0) : '—'} hint={`${approved} approved`} />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <ChartCard
          title="Where signals drop out"
          subtitle={`Combined, last ${hist.length} cycles`}
          chart={
            <Funnel
              stages={[
                { label: 'Generated', value: totals.generated },
                { label: 'Strategy ✓', value: totals.strategy },
                { label: 'Risk ✓', value: totals.risk },
                { label: 'Simulation ✓', value: totals.sim },
                { label: 'Executed', value: totals.executed },
              ]}
            />
          }
          table={
            <DataTable
              rows={[...hist].reverse()}
              rowKey={(r) => r.cycle_id}
              maxHeight={260}
              columns={[
                { key: 'ts', header: 'Cycle', render: (r) => time(r.started_at) },
                { key: 'g', header: 'Gen', align: 'right', render: (r) => r.signals_generated },
                { key: 's', header: 'Strat', align: 'right', render: (r) => r.strategies_assigned },
                { key: 'r', header: 'Risk', align: 'right', render: (r) => r.risk_approved },
                { key: 'm', header: 'Sim', align: 'right', render: (r) => r.sim_approved },
                { key: 'e', header: 'Exec', align: 'right', render: (r) => r.trades_executed },
              ]}
            />
          }
        />
        <ChartCard
          title="Top rejection reasons"
          subtitle="Debate and decision stage"
          chart={<HBars data={data.rejections.map((r) => ({ label: r.reason, value: r.count }))} valueLabel="Rejections" labelWidth={170} />}
          table={
            <DataTable
              rows={data.rejections}
              rowKey={(r) => r.reason}
              columns={[
                { key: 'reason', header: 'Reason', render: (r) => <span className="block max-w-[240px] truncate">{r.reason}</span> },
                { key: 'count', header: 'Count', align: 'right', render: (r) => r.count },
              ]}
            />
          }
        />
        <ChartCard
          title="Decisions by strategy"
          chart={<HBars data={data.strategies.map((s) => ({ label: titleCase(s.strategy), value: s.count }))} valueLabel="Decisions" />}
          table={
            <DataTable
              rows={data.strategies}
              rowKey={(r) => r.strategy}
              columns={[
                { key: 's', header: 'Strategy', render: (r) => titleCase(r.strategy) },
                { key: 'c', header: 'Decisions', align: 'right', render: (r) => r.count },
                { key: 'a', header: 'Approved', align: 'right', render: (r) => r.approved },
                { key: 'conf', header: 'Avg conf.', align: 'right', render: (r) => num(r.avg_confidence) },
              ]}
            />
          }
        />
      </div>

      <Card
        title="Decision log"
        subtitle={`${rows.length} shown · agent scores out of 10`}
        bodyClassName={isPlaceholderData ? 'p-0 opacity-60 transition-opacity' : 'p-0 transition-opacity'}
      >
        <DecisionsTable rows={rows} maxHeight={600} />
      </Card>
    </div>
  )
}
