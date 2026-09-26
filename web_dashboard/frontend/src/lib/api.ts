import { keepPreviousData, useQuery } from '@tanstack/react-query'

export type ServiceStatus = {
  status: 'ONLINE' | 'IDLE' | 'OFFLINE' | 'UNKNOWN'
  last_ts: string | null
  last_event: string
  age_min: number | null
}

export type Cycle = {
  cycle_id: string
  started_at: string
  completed_at: string | null
  had_error: number
  regime: string | null
  vix: number | null
  breadth: number | null
  pcr: number | null
  signals_generated: number
  strategies_assigned: number
  risk_approved: number
  sim_approved: number
  trades_executed: number
  cycle_ms: number
  decision_passed?: number
  status?: 'COMPLETE' | 'RUNNING' | 'ERROR'
}

export type Decision = {
  id: number
  ts: string
  cycle_id: string
  symbol: string
  strategy: string
  direction: string | null
  confidence: number | null
  decision: string
  rejection_reason: string | null
  technical_score: number | null
  risk_score: number | null
  macro_score: number | null
  sentiment_score: number | null
  regime_score: number | null
  position_modifier: number | null
}

export type OpenPosition = {
  order_id: string
  symbol: string
  direction: string
  quantity: number | null
  entry_price: number | null
  stop_loss: number | null
  target: number | null
  strategy: string
  confidence: number | null
  opened_at: string
  exposure: number
}

export type ClosedTrade = {
  order_id: string
  symbol: string
  direction: string
  quantity: number | null
  entry_price: number | null
  exit_price: number | null
  stop_loss: number | null
  target: number | null
  strategy: string
  pnl: number
  reason: string
  opened_at: string | null
  closed_at: string | null
}

export type EquityPoint = { ts: string; pnl: number; cumulative: number; equity: number }

export type TradeStats = {
  total_trades: number
  win_rate: number | null
  total_pnl: number
  realized_today: number
  avg_win: number | null
  avg_loss: number | null
  profit_factor: number | null
  max_drawdown: number
  open_count: number
  open_exposure: number
}

export type ScheduleSlot = {
  name: string
  label: string
  time: string
  status: 'DONE' | 'MISSED' | 'PENDING' | 'WEEKEND_ONLY' | 'WEEKDAY_ONLY'
}

export type Scheduler = {
  slots: ScheduleSlot[]
  next: { name: string; label: string; time: string; seconds_until: number } | null
}

export type Overview = {
  server_time: string
  mode: 'PAPER' | 'LIVE'
  service: ServiceStatus
  today_events: number
  capital: number
  stats: TradeStats
  open_positions: OpenPosition[]
  equity_curve: EquityPoint[]
  cycle: Partial<Cycle>
  scheduler: Scheduler
  latest_approved: Decision | null
  recent_decisions: Decision[]
}

export type Trades = {
  capital: number
  open_positions: OpenPosition[]
  closed_trades: ClosedTrade[]
  equity_curve: EquityPoint[]
  by_strategy: { strategy: string; trades: number; wins: number; pnl: number; win_rate: number }[]
  by_day: { date: string; trades: number; wins: number; pnl: number }[]
  stats: TradeStats
}

export type Decisions = {
  decisions: Decision[]
  rejections: { reason: string; count: number }[]
  strategies: { strategy: string; count: number; avg_confidence: number | null; approved: number }[]
  funnel_history: Pick<
    Cycle,
    | 'cycle_id'
    | 'started_at'
    | 'signals_generated'
    | 'strategies_assigned'
    | 'risk_approved'
    | 'sim_approved'
    | 'trades_executed'
  >[]
}

export type AgentStat = { agent: string; event_count: number; error_count: number; last_seen: string }

export type TelemetryEvent = {
  id: number
  ts: string
  cycle_id: string | null
  event_type: string
  source_agent: string | null
  payload: Record<string, unknown> | string
}

export type Health = {
  service: ServiceStatus
  scheduler: Scheduler
  cycles: Cycle[]
  agents: AgentStat[]
  events: TelemetryEvent[]
}

export type Eod = { daily: Record<string, unknown> | null; report_text: string | null }

const REFRESH_MS = 5000

export type Session = { authenticated: boolean; configured: boolean }

let unauthorizedHandler: () => void = () => {}
/** Called whenever the API answers 401 (session expired / logged out elsewhere). */
export function onUnauthorized(handler: () => void) {
  unauthorizedHandler = handler
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { credentials: 'same-origin' })
  if (res.status === 401) {
    unauthorizedHandler()
    throw new Error('Session expired — please sign in again')
  }
  if (!res.ok) throw new Error(`${path} → HTTP ${res.status}`)
  return res.json() as Promise<T>
}

export const useSession = () =>
  useQuery({ queryKey: ['session'], queryFn: () => getJson<Session>('/api/auth/session'), staleTime: Infinity })

export async function login(password: string): Promise<void> {
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  })
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: string }
    throw new Error(body.detail || `Sign-in failed (HTTP ${res.status})`)
  }
}

export async function logout(): Promise<void> {
  await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' })
}

// ── Zerodha (Kite) daily login ─────────────────────────────────────────────

export type KiteStatus = {
  configured: boolean
  connected: boolean
  user_id: string
  user_name: string
  login_at: string | null
  expires_at: string | null
  auto_login: KiteAutoLoginStatus
}

export type KiteAutoLoginStatus = {
  enabled: boolean
  last_attempt: string | null
  ok: boolean | null
  message: string
  actor: 'engine' | 'dashboard' | null
  blocked: boolean
}

export const useKiteStatus = () =>
  useQuery({ queryKey: ['kite'], queryFn: () => getJson<KiteStatus>('/api/kite/status'), refetchInterval: 30_000 })

/** Returns the Zerodha login URL (with a one-time state) to navigate to. */
export async function kiteLoginUrl(): Promise<string> {
  const res = await fetch('/api/kite/login', { method: 'POST', credentials: 'same-origin' })
  const body = (await res.json().catch(() => ({}))) as { url?: string; detail?: string }
  if (!res.ok || !body.url) throw new Error(body.detail || `Could not start Zerodha login (HTTP ${res.status})`)
  return body.url
}

/** Run the automatic Zerodha login now (user ID + password + TOTP saved in Settings). */
export async function kiteAutoLogin(): Promise<{ ok: boolean; message: string }> {
  const res = await fetch('/api/kite/auto-login', { method: 'POST', credentials: 'same-origin' })
  if (res.status === 401) {
    unauthorizedHandler()
    throw new Error('Session expired — please sign in again')
  }
  const body = (await res.json().catch(() => ({}))) as { ok?: boolean; message?: string; detail?: string }
  return { ok: Boolean(body.ok), message: body.message || body.detail || `Login failed (HTTP ${res.status})` }
}

export async function kiteDisconnect(): Promise<void> {
  await fetch('/api/kite/disconnect', { method: 'POST', credentials: 'same-origin' })
}

// ── Settings: broker credentials (values are never returned, only status) ──

export type BrokerId = 'kite' | 'dhan' | 'angelone'

export type BrokerField = {
  label: string
  secret: boolean
  set: boolean
  source: 'settings' | 'env' | null
  hint: string
  optional: boolean
}

export type BrokerStatus = {
  label: string
  fields: Record<string, BrokerField>
  complete: boolean
  updated_at: string | null
}

export type CredentialStatus = {
  unlocked: boolean
  lock_reason: string | null
  brokers: Record<BrokerId, BrokerStatus>
}

export type AuditEntry = { ts: string; action: 'save' | 'remove'; broker: BrokerId; fields: string[]; actor: string }

export const useBrokerSettings = () =>
  useQuery({
    queryKey: ['settings', 'brokers'],
    queryFn: () => getJson<CredentialStatus>('/api/settings/brokers'),
    refetchInterval: 30_000,
  })

export const useSettingsAudit = () =>
  useQuery({
    queryKey: ['settings', 'audit'],
    queryFn: () => getJson<{ entries: AuditEntry[] }>('/api/settings/audit'),
    refetchInterval: 60_000,
  })

async function sendJson<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (res.status === 401) {
    unauthorizedHandler()
    throw new Error('Session expired — please sign in again')
  }
  const data = (await res.json().catch(() => ({}))) as T & { detail?: string }
  if (!res.ok) throw new Error(data.detail || `Request failed (HTTP ${res.status})`)
  return data
}

export const saveBrokerCredentials = (broker: BrokerId, password: string, values: Record<string, string>) =>
  sendJson<{ changed: string[] }>('PUT', `/api/settings/brokers/${broker}`, { password, values })

export const removeBrokerCredentials = (broker: BrokerId, password: string) =>
  sendJson<{ removed: boolean }>('POST', `/api/settings/brokers/${broker}/remove`, { password })

export const testBrokerConnection = (broker: BrokerId) =>
  sendJson<{ ok: boolean; message: string }>('POST', `/api/settings/brokers/${broker}/test`)

function usePolled<T>(key: string, path: string, refetchInterval = REFRESH_MS) {
  return useQuery({
    queryKey: [key, path],
    queryFn: () => getJson<T>(path),
    refetchInterval,
    // Hold the previous render while refetching — no skeleton flash.
    placeholderData: keepPreviousData,
  })
}

export const useOverview = () => usePolled<Overview>('overview', '/api/overview')
export const useTrades = () => usePolled<Trades>('trades', '/api/trades', 10_000)
export const useDecisions = (decision = '') =>
  usePolled<Decisions>('decisions', `/api/decisions?limit=500${decision ? `&decision=${decision}` : ''}`)
export const useHealth = () => usePolled<Health>('health', '/api/health')
export const useEod = () => usePolled<Eod>('eod', '/api/eod', 60_000)
