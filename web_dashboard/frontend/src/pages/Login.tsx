import { BrainCircuit, Eye, EyeOff, Lock } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { login } from '../lib/api'

export default function LoginPage({ configured, onSuccess }: { configured: boolean; onSuccess: () => void }) {
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!password) {
      setError('Enter your password')
      return
    }
    setBusy(true)
    setError('')
    try {
      await login(password)
      setPassword('')
      onSuccess()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-full place-items-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <span className="grid size-11 place-items-center rounded-xl bg-accent-soft text-accent">
            <BrainCircuit className="size-6" aria-hidden />
          </span>
          <div>
            <h1 className="text-lg font-semibold">AI Trading Brain</h1>
            <p className="text-[13px] text-ink-3">Sign in to the control tower</p>
          </div>
        </div>

        <form onSubmit={submit} className="rounded-xl border border-line bg-panel p-5" noValidate>
          {configured ? (
            <>
              <label htmlFor="password" className="mb-1.5 block text-xs text-ink-2">
                Password
              </label>
              <div className="relative">
                <Lock className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-3" aria-hidden />
                <input
                  id="password"
                  type={show ? 'text' : 'password'}
                  autoComplete="current-password"
                  autoFocus
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value)
                    if (error) setError('')
                  }}
                  aria-invalid={!!error}
                  aria-describedby={error ? 'login-error' : undefined}
                  className="h-10 w-full rounded-lg border border-line-strong bg-panel-2 pr-10 pl-9 text-sm outline-none focus:border-accent"
                />
                <button
                  type="button"
                  onClick={() => setShow(!show)}
                  className="absolute top-1/2 right-2 -translate-y-1/2 rounded p-1 text-ink-3 hover:text-ink-2"
                  aria-label={show ? 'Hide password' : 'Show password'}
                >
                  {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
              {error && (
                <p id="login-error" role="alert" className="mt-2 text-[13px] text-loss">
                  {error}
                </p>
              )}
              <button
                type="submit"
                disabled={busy}
                className="mt-4 h-10 w-full rounded-lg bg-accent text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                {busy ? 'Signing in…' : 'Sign in'}
              </button>
            </>
          ) : (
            <div className="space-y-2 text-[13px]">
              <p className="font-medium text-warn">No dashboard password is set yet</p>
              <p className="text-ink-2">The dashboard stays locked until one is set. On the machine running it:</p>
              <pre className="overflow-x-auto rounded-lg bg-panel-2 px-3 py-2 font-mono text-[12px] text-ink">
                python -m web_dashboard.set_password
              </pre>
              <p className="text-ink-3">Then restart the dashboard server and reload this page.</p>
            </div>
          )}
        </form>
        <p className="mt-4 text-center text-[11px] text-ink-3">Read-only view · sessions expire automatically</p>
      </div>
    </div>
  )
}
