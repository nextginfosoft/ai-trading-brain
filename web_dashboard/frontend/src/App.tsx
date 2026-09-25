import { useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { Activity, BrainCircuit, CandlestickChart, Filter, LayoutDashboard, LogOut } from 'lucide-react'
import { useEffect, useState } from 'react'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { Badge, QueryState, type Tone } from './components/ui'
import { logout, onUnauthorized, useOverview, useSession, type Session } from './lib/api'
import { duration, marketSession, num, titleCase } from './lib/format'
import HealthPage from './pages/Health'
import LoginPage from './pages/Login'
import OverviewPage from './pages/Overview'
import SignalsPage from './pages/Signals'
import TradesPage from './pages/Trades'

const NAV = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/trades', label: 'Trades & P&L', icon: CandlestickChart },
  { to: '/signals', label: 'Signals & decisions', icon: Filter },
  { to: '/health', label: 'System health', icon: Activity },
]

const SERVICE_TONE: Record<string, Tone> = { ONLINE: 'profit', IDLE: 'warn', OFFLINE: 'loss', UNKNOWN: 'neutral' }

function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), intervalMs)
    return () => clearInterval(id)
  }, [intervalMs])
  return now
}

function StatusBar() {
  const { data, dataUpdatedAt, isError } = useOverview()
  const now = useNow()
  const session = marketSession(now)
  const next = data?.scheduler.next
  const secsLeft = next ? next.seconds_until - Math.floor((now.getTime() - dataUpdatedAt) / 1000) : null

  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs">
      <div className="flex items-center gap-2">
        {data?.mode === 'LIVE' ? <Badge tone="loss" dot>LIVE</Badge> : <Badge tone="accent" dot>PAPER</Badge>}
        {isError ? (
          <Badge tone="loss" dot>API offline</Badge>
        ) : (
          data && (
            <Badge tone={SERVICE_TONE[data.service.status] ?? 'neutral'} dot>
              Engine {data.service.status.toLowerCase()}
            </Badge>
          )
        )}
      </div>
      <span className="flex items-center gap-1.5 text-ink-2">
        <span
          className={clsx('size-1.5 rounded-full', session.open ? 'pulse-dot bg-profit' : 'bg-ink-3')}
          aria-hidden
        />
        {session.label}
      </span>
      {data?.cycle.regime && (
        <span className="text-ink-3">
          Regime <span className="text-ink-2">{titleCase(data.cycle.regime)}</span>
        </span>
      )}
      {data?.cycle.vix != null && (
        <span className="text-ink-3">
          VIX <span className="num text-ink-2">{num(data.cycle.vix, 2)}</span>
        </span>
      )}
      {next && secsLeft != null && (
        <span className="text-ink-3">
          Next: <span className="text-ink-2">{next.label}</span> at <span className="num text-ink-2">{next.time}</span>{' '}
          <span className="num text-ink-3">({duration(Math.max(secsLeft, 0))})</span>
        </span>
      )}
      <span className="ml-auto num text-ink-3">{now.toLocaleTimeString('en-IN', { hour12: false })} IST</span>
    </div>
  )
}

export default function App() {
  const queryClient = useQueryClient()
  const session = useSession()

  useEffect(() => {
    onUnauthorized(() => {
      queryClient.setQueryData<Session>(['session'], (s) => ({ configured: s?.configured ?? true, authenticated: false }))
    })
  }, [queryClient])

  if (!session.data) return <QueryState isLoading={session.isLoading} error={session.error} />
  if (!session.data.authenticated)
    return (
      <LoginPage
        configured={session.data.configured}
        onSuccess={() => {
          queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== 'session' })
          queryClient.setQueryData<Session>(['session'], { configured: true, authenticated: true })
        }}
      />
    )

  const signOut = async () => {
    await logout()
    queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== 'session' })
    queryClient.setQueryData<Session>(['session'], { configured: true, authenticated: false })
  }

  return <Shell onSignOut={signOut} />
}

function Shell({ onSignOut }: { onSignOut: () => void }) {
  return (
    <div className="flex h-full min-h-0">
      <aside className="hidden w-56 shrink-0 flex-col border-r border-line bg-panel md:flex">
        <div className="flex items-center gap-2.5 px-4 py-4">
          <span className="grid size-8 place-items-center rounded-lg bg-accent-soft text-accent">
            <BrainCircuit className="size-[18px]" aria-hidden />
          </span>
          <div className="leading-tight">
            <div className="text-[13px] font-semibold">AI Trading Brain</div>
            <div className="text-[11px] text-ink-3">Control tower</div>
          </div>
        </div>
        <nav className="flex flex-col gap-0.5 px-2" aria-label="Main">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] transition-colors',
                  isActive ? 'bg-panel-3 text-ink' : 'text-ink-3 hover:bg-panel-2 hover:text-ink-2',
                )
              }
            >
              <Icon className="size-4" aria-hidden />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto space-y-3 px-4 py-4">
          <button
            onClick={onSignOut}
            className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] text-ink-3 hover:bg-panel-2 hover:text-ink-2"
          >
            <LogOut className="size-4" aria-hidden />
            Sign out
          </button>
          <p className="text-[11px] leading-relaxed text-ink-3">Read-only view. Refreshes every 5s.</p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 border-b border-line bg-page/90 px-4 py-3 backdrop-blur md:px-6">
          <nav className="-mx-1 mb-2.5 flex gap-1 overflow-x-auto md:hidden" aria-label="Main">
            {NAV.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  clsx(
                    'rounded-md px-2.5 py-1 text-xs whitespace-nowrap',
                    isActive ? 'bg-panel-3 text-ink' : 'text-ink-3',
                  )
                }
              >
                {label}
              </NavLink>
            ))}
            <button onClick={onSignOut} className="ml-auto rounded-md px-2.5 py-1 text-xs whitespace-nowrap text-ink-3">
              Sign out
            </button>
          </nav>
          <StatusBar />
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-6">
          <div className="mx-auto max-w-[1440px]">
            <Routes>
              <Route path="/" element={<OverviewPage />} />
              <Route path="/trades" element={<TradesPage />} />
              <Route path="/signals" element={<SignalsPage />} />
              <Route path="/health" element={<HealthPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </div>
        </main>
      </div>
    </div>
  )
}
