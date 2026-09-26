import { useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { CheckCircle2, Eye, EyeOff, KeyRound, Lock, PlugZap, ShieldAlert, Trash2, TriangleAlert } from 'lucide-react'
import { useState, type FormEvent, type ReactNode } from 'react'
import { KiteConnectControl } from '../components/KiteConnect'
import { Badge, Card, DataTable, EmptyState, QueryState } from '../components/ui'
import {
  removeBrokerCredentials,
  saveBrokerCredentials,
  testBrokerConnection,
  useBrokerSettings,
  useSettingsAudit,
  type BrokerId,
  type BrokerStatus,
} from '../lib/api'
import { time } from '../lib/format'

const BROKER_ORDER: BrokerId[] = ['kite', 'dhan', 'angelone']

const BROKER_NOTES: Record<BrokerId, ReactNode> = {
  kite: (
    <>
      From <span className="text-ink-2">developers.kite.trade</span> → your app. Zerodha requires a login every
      morning: use <span className="text-ink-2">Connect Zerodha</span> after saving.
    </>
  ),
  dhan: (
    <>
      From <span className="text-ink-2">web.dhan.co</span> → My Profile → Access DhanHQ APIs. Access tokens expire;
      replace the token here when you renew it.
    </>
  ),
  angelone: (
    <>
      From <span className="text-ink-2">smartapi.angelbroking.com</span>. The TOTP secret is the base32 key shown when
      you enable TOTP. These allow a fully automatic daily login, so keep this dashboard's password strong.
    </>
  ),
}

// Until the engine reads saved Dhan/AngelOne values (next update), say so plainly.
const ENGINE_NOTE: Partial<Record<BrokerId, string>> = {
  dhan: 'Test connection uses these now. The trading engine switches to saved values in the next update; until then it reads the server .env.',
  angelone:
    'Test connection uses these now. The trading engine switches to saved values in the next update; until then it reads the server .env.',
}

export default function SettingsPage() {
  const { data, isLoading, error } = useBrokerSettings()
  if (!data) return <QueryState isLoading={isLoading} error={error} />

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Broker settings</h1>
        <p className="mt-1 max-w-3xl text-[13px] text-ink-3">
          Credentials are encrypted on the server and never shown again after saving — only whether a value is set and
          its last 4 characters. Saving or removing needs your dashboard password. Trading stays in paper mode.
        </p>
      </div>

      {!data.unlocked && (
        <div role="alert" className="flex items-start gap-2 rounded-lg bg-loss-soft px-3 py-2.5 text-[13px] text-loss">
          <Lock className="mt-0.5 size-4 shrink-0" aria-hidden />
          <div>
            <div className="font-medium">Credential store is locked</div>
            <div className="text-loss/90">
              {data.lock_reason}. Saved credentials can't be changed until the server has a valid CREDENTIALS_KEY;
              values in the server .env still work.
            </div>
          </div>
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-3">
        {BROKER_ORDER.map((id) => (
          <BrokerCard key={id} id={id} status={data.brokers[id]} locked={!data.unlocked} />
        ))}
      </div>

      <AuditCard />
    </div>
  )
}

function statusBadge(status: BrokerStatus) {
  const setCount = Object.values(status.fields).filter((f) => f.set).length
  if (status.complete) return <Badge tone="profit" dot>Complete</Badge>
  if (setCount) return <Badge tone="warn" dot>Incomplete</Badge>
  return <Badge dot>Not set</Badge>
}

function BrokerCard({ id, status, locked }: { id: BrokerId; status: BrokerStatus; locked: boolean }) {
  const queryClient = useQueryClient()
  const [mode, setMode] = useState<'view' | 'edit' | 'remove'>('view')
  const [values, setValues] = useState<Record<string, string>>({})
  const [shown, setShown] = useState<Record<string, boolean>>({})
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [test, setTest] = useState<{ ok: boolean; message: string } | null>(null)
  const [testing, setTesting] = useState(false)

  const anySaved = Object.values(status.fields).some((f) => f.source === 'settings')

  const reset = () => {
    setMode('view')
    setValues({})
    setShown({})
    setPassword('')
    setError('')
  }

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['settings'] })
    queryClient.invalidateQueries({ queryKey: ['kite'] })
  }

  async function onSave(e: FormEvent) {
    e.preventDefault()
    const filled = Object.fromEntries(Object.entries(values).filter(([, v]) => v.trim()))
    if (!Object.keys(filled).length) return setError('Enter at least one value to change')
    if (!password) return setError('Enter your dashboard password to confirm')
    setBusy(true)
    setError('')
    try {
      const { changed } = await saveBrokerCredentials(id, password, filled)
      reset()
      setTest(null)
      setNotice(`Saved: ${changed.map((f) => status.fields[f]?.label ?? f).join(', ')}`)
      refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  async function onRemove(e: FormEvent) {
    e.preventDefault()
    if (!password) return setError('Enter your dashboard password to confirm')
    setBusy(true)
    setError('')
    try {
      await removeBrokerCredentials(id, password)
      reset()
      setTest(null)
      setNotice('Saved values removed')
      refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Remove failed')
    } finally {
      setBusy(false)
    }
  }

  async function onTest() {
    setTesting(true)
    setTest(null)
    try {
      setTest(await testBrokerConnection(id))
    } catch (err) {
      setTest({ ok: false, message: err instanceof Error ? err.message : 'Test failed' })
    } finally {
      setTesting(false)
    }
  }

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <KeyRound className="size-4 text-ink-3" aria-hidden />
          {status.label}
        </span>
      }
      subtitle={status.updated_at ? `Updated ${time(status.updated_at)}` : 'Not changed from this page yet'}
      actions={statusBadge(status)}
    >
      <p className="mb-3 text-xs leading-relaxed text-ink-3">{BROKER_NOTES[id]}</p>

      {mode === 'view' && (
        <dl className="space-y-1.5">
          {Object.entries(status.fields).map(([key, f]) => (
            <div key={key} className="flex items-center justify-between gap-3 rounded-lg bg-panel-2 px-3 py-2">
              <dt className="text-[13px] text-ink-2">{f.label}</dt>
              <dd className="flex items-center gap-2 text-xs">
                {f.set ? (
                  <>
                    <span className="num font-mono text-ink">{f.hint}</span>
                    <span className="text-ink-3">{f.source === 'settings' ? 'Settings' : '.env'}</span>
                  </>
                ) : (
                  <span className="text-ink-3">Not set</span>
                )}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {mode === 'edit' && (
        <form onSubmit={onSave} className="space-y-2.5" noValidate autoComplete="off">
          {Object.entries(status.fields).map(([key, f]) => {
            const inputId = `${id}-${key}`
            return (
              <div key={key}>
                <label htmlFor={inputId} className="mb-1 block text-xs text-ink-2">
                  {f.label}
                  {f.set && <span className="ml-1.5 text-ink-3">(current {f.hint})</span>}
                </label>
                <div className="relative">
                  <input
                    id={inputId}
                    type={f.secret && !shown[key] ? 'password' : 'text'}
                    autoComplete="new-password"
                    spellCheck={false}
                    value={values[key] ?? ''}
                    onChange={(e) => {
                      setValues({ ...values, [key]: e.target.value })
                      if (error) setError('')
                    }}
                    placeholder={f.set ? 'Leave blank to keep current' : `Enter ${f.label.toLowerCase()}`}
                    className={clsx(
                      'h-9 w-full rounded-lg border border-line-strong bg-panel-2 px-3 font-mono text-[13px] outline-none placeholder:font-sans placeholder:text-ink-3 focus:border-accent',
                      f.secret && 'pr-9',
                    )}
                  />
                  {f.secret && (
                    <button
                      type="button"
                      onClick={() => setShown({ ...shown, [key]: !shown[key] })}
                      className="absolute top-1/2 right-2 -translate-y-1/2 rounded p-0.5 text-ink-3 hover:text-ink-2"
                      aria-label={shown[key] ? `Hide ${f.label}` : `Show ${f.label}`}
                    >
                      {shown[key] ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                    </button>
                  )}
                </div>
              </div>
            )
          })}
          <ConfirmPassword id={`${id}-confirm`} value={password} onChange={(v) => { setPassword(v); if (error) setError('') }} />
          {error && <FormError id={`${id}-error`}>{error}</FormError>}
          <div className="flex gap-2 pt-1">
            <button type="submit" disabled={busy}
              className="h-8 rounded-lg bg-accent px-3 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50">
              {busy ? 'Saving…' : 'Save'}
            </button>
            <button type="button" onClick={reset} className="h-8 rounded-lg px-3 text-xs text-ink-2 hover:bg-panel-3">
              Cancel
            </button>
          </div>
        </form>
      )}

      {mode === 'remove' && (
        <form onSubmit={onRemove} className="space-y-2.5" noValidate>
          <p className="text-[13px] text-ink-2">
            Remove the values saved on this page for {status.label}? Values in the server .env, if any, still apply.
          </p>
          <ConfirmPassword id={`${id}-confirm-remove`} value={password} onChange={(v) => { setPassword(v); if (error) setError('') }} />
          {error && <FormError id={`${id}-error`}>{error}</FormError>}
          <div className="flex gap-2">
            <button type="submit" disabled={busy}
              className="h-8 rounded-lg bg-loss px-3 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50">
              {busy ? 'Removing…' : 'Remove saved values'}
            </button>
            <button type="button" onClick={reset} className="h-8 rounded-lg px-3 text-xs text-ink-2 hover:bg-panel-3">
              Cancel
            </button>
          </div>
        </form>
      )}

      {mode === 'view' && (
        <>
          {notice && (
            <p role="status" className="mt-3 flex items-center gap-1.5 text-xs text-profit">
              <CheckCircle2 className="size-3.5" aria-hidden />
              {notice}
            </p>
          )}
          {test && (
            <p role="status" className={clsx('mt-3 flex items-start gap-1.5 text-xs', test.ok ? 'text-profit' : 'text-loss')}>
              {test.ok ? <CheckCircle2 className="mt-px size-3.5 shrink-0" aria-hidden /> : <TriangleAlert className="mt-px size-3.5 shrink-0" aria-hidden />}
              {test.message}
            </p>
          )}
          {ENGINE_NOTE[id] && <p className="mt-3 text-[11px] leading-relaxed text-ink-3">{ENGINE_NOTE[id]}</p>}
          {id === 'kite' && status.complete && (
            <div className="mt-3 flex items-center gap-2 text-xs">
              <span className="text-ink-3">Today's login:</span>
              <KiteConnectControl />
            </div>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              onClick={() => { setMode('edit'); setNotice('') }}
              disabled={locked}
              title={locked ? 'Credential store is locked' : undefined}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-line-strong px-3 text-xs text-ink hover:bg-panel-3 disabled:opacity-40"
            >
              <KeyRound className="size-3.5" aria-hidden />
              {Object.values(status.fields).some((f) => f.set) ? 'Update' : 'Add credentials'}
            </button>
            <button
              onClick={onTest}
              disabled={testing}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-line-strong px-3 text-xs text-ink hover:bg-panel-3 disabled:opacity-40"
            >
              <PlugZap className="size-3.5" aria-hidden />
              {testing ? 'Testing…' : 'Test connection'}
            </button>
            {anySaved && (
              <button
                onClick={() => { setMode('remove'); setNotice('') }}
                disabled={locked}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg px-3 text-xs text-loss hover:bg-loss-soft disabled:opacity-40"
              >
                <Trash2 className="size-3.5" aria-hidden />
                Remove
              </button>
            )}
          </div>
        </>
      )}
    </Card>
  )
}

function ConfirmPassword({ id, value, onChange }: { id: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="rounded-lg border border-line bg-panel-2/60 p-2.5">
      <label htmlFor={id} className="mb-1 flex items-center gap-1.5 text-xs text-ink-2">
        <ShieldAlert className="size-3.5 text-warn" aria-hidden />
        Dashboard password (to confirm)
      </label>
      <input
        id={id}
        type="password"
        autoComplete="current-password"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 w-full rounded-lg border border-line-strong bg-panel px-3 text-[13px] outline-none focus:border-accent"
      />
    </div>
  )
}

function FormError({ id, children }: { id: string; children: ReactNode }) {
  return (
    <p id={id} role="alert" className="text-[13px] text-loss">
      {children}
    </p>
  )
}

function AuditCard() {
  const { data } = useSettingsAudit()
  const entries = data?.entries ?? []
  const label: Record<string, string> = { kite: 'Zerodha (Kite)', dhan: 'Dhan', angelone: 'AngelOne' }
  return (
    <Card title="Recent changes" subtitle="What changed and when — values are never recorded" bodyClassName="p-0">
      <DataTable
        rows={entries}
        rowKey={(r, i) => `${r.ts}-${i}`}
        maxHeight={280}
        empty={<EmptyState title="No changes yet" />}
        columns={[
          { key: 'ts', header: 'When', render: (r) => <span className="text-ink-3">{time(r.ts)}</span> },
          { key: 'broker', header: 'Broker', render: (r) => label[r.broker] ?? r.broker },
          {
            key: 'action',
            header: 'Action',
            render: (r) => <Badge tone={r.action === 'remove' ? 'loss' : 'accent'}>{r.action === 'remove' ? 'Removed' : 'Saved'}</Badge>,
          },
          { key: 'fields', header: 'Fields', render: (r) => <span className="text-ink-2">{r.fields.join(', ') || '—'}</span> },
        ]}
      />
    </Card>
  )
}
