import { useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { CheckCircle2, Link2, TriangleAlert, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { kiteDisconnect, kiteLoginUrl, useKiteStatus } from '../lib/api'
import { time } from '../lib/format'
import { Badge } from './ui'

/** Header control: Zerodha connection state + the daily "Connect Zerodha" login. */
export function KiteConnectControl() {
  const { data } = useKiteStatus()
  const queryClient = useQueryClient()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  if (!data?.configured) return null

  if (data.connected) {
    return (
      <span className="inline-flex items-center gap-1.5">
        <Badge tone="profit" dot>
          Zerodha connected
        </Badge>
        <span className="hidden text-ink-3 lg:inline" title={`Logged in ${time(data.login_at)} as ${data.user_id}`}>
          until <span className="num text-ink-2">{time(data.expires_at)}</span>
        </span>
        <button
          onClick={async () => {
            await kiteDisconnect()
            queryClient.invalidateQueries({ queryKey: ['kite'] })
          }}
          className="rounded p-0.5 text-ink-3 hover:bg-panel-3 hover:text-ink-2"
          aria-label="Disconnect Zerodha"
          title="Disconnect Zerodha"
        >
          <X className="size-3.5" />
        </button>
      </span>
    )
  }

  return (
    <span className="inline-flex items-center gap-2">
      <button
        disabled={busy}
        onClick={async () => {
          setBusy(true)
          setError('')
          try {
            window.location.href = await kiteLoginUrl()
          } catch (e) {
            setError(e instanceof Error ? e.message : 'Could not start Zerodha login')
            setBusy(false)
          }
        }}
        className="inline-flex items-center gap-1.5 rounded-md bg-warn-soft px-2 py-0.5 text-[11px] font-medium text-warn hover:opacity-90 disabled:opacity-50"
      >
        <Link2 className="size-3.5" aria-hidden />
        {busy ? 'Opening Zerodha…' : 'Connect Zerodha'}
      </button>
      {error && <span className="text-loss">{error}</span>}
    </span>
  )
}

/** One-shot banner after returning from Zerodha (/?kite=connected|error&reason=...). */
export function KiteReturnBanner() {
  const queryClient = useQueryClient()
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const outcome = params.get('kite')
    if (!outcome) return
    setMsg(
      outcome === 'connected'
        ? { ok: true, text: 'Zerodha connected. Live Kite data is active for today.' }
        : { ok: false, text: params.get('reason') || 'Zerodha login failed.' },
    )
    queryClient.invalidateQueries({ queryKey: ['kite'] })
    params.delete('kite')
    params.delete('reason')
    const rest = params.toString()
    window.history.replaceState(null, '', window.location.pathname + (rest ? `?${rest}` : ''))
  }, [queryClient])

  if (!msg) return null
  return (
    <div
      role="status"
      className={clsx(
        'mb-4 flex items-center gap-2 rounded-lg px-3 py-2 text-[13px]',
        msg.ok ? 'bg-profit-soft text-profit' : 'bg-loss-soft text-loss',
      )}
    >
      {msg.ok ? <CheckCircle2 className="size-4" aria-hidden /> : <TriangleAlert className="size-4" aria-hidden />}
      <span className="flex-1">{msg.text}</span>
      <button onClick={() => setMsg(null)} aria-label="Dismiss" className="rounded p-0.5 hover:bg-black/10">
        <X className="size-4" />
      </button>
    </div>
  )
}
