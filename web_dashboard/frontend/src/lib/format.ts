const inr = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })
const inr2 = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

/** ₹1,23,456 — Indian digit grouping. */
export function money(v: number | null | undefined, decimals = false): string {
  if (v == null || Number.isNaN(v)) return '—'
  const s = (decimals ? inr2 : inr).format(Math.abs(v))
  return `${v < 0 ? '−' : ''}₹${s}`
}

/** Signed money: +₹1,234 / −₹560. */
export function signedMoney(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  if (v === 0) return '₹0'
  return `${v > 0 ? '+' : '−'}₹${inr.format(Math.abs(v))}`
}

/** Compact: ₹2.0L, ₹1.2Cr, ₹45.3K. */
export function compactMoney(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  const a = Math.abs(v)
  const sign = v < 0 ? '−' : ''
  if (a >= 1e7) return `${sign}₹${(a / 1e7).toFixed(2)}Cr`
  if (a >= 1e5) return `${sign}₹${(a / 1e5).toFixed(2)}L`
  if (a >= 1e3) return `${sign}₹${(a / 1e3).toFixed(1)}K`
  return `${sign}₹${a.toFixed(0)}`
}

export function price(v: number | null | undefined): string {
  return v == null || Number.isNaN(v) ? '—' : inr2.format(v)
}

export function pct(v: number | null | undefined, digits = 1): string {
  return v == null || Number.isNaN(v) ? '—' : `${(v * 100).toFixed(digits)}%`
}

export function num(v: number | null | undefined, digits = 1): string {
  return v == null || Number.isNaN(v) ? '—' : v.toFixed(digits)
}

/** "2026-09-25T14:03:11" → "14:03:11" (or "25 Sep 14:03" when not today). */
export function time(ts: string | null | undefined): string {
  if (!ts) return '—'
  const d = new Date(ts.replace(' ', 'T'))
  if (Number.isNaN(d.getTime())) return ts
  const today = new Date().toDateString() === d.toDateString()
  return today
    ? d.toLocaleTimeString('en-IN', { hour12: false })
    : d.toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false })
}

export function shortDate(d: string): string {
  const dt = new Date(d)
  return Number.isNaN(dt.getTime()) ? d : dt.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
}

export function duration(seconds: number): string {
  if (seconds < 0) return '—'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  return h ? `${h}h ${m}m` : m ? `${m}m ${s}s` : `${s}s`
}

export function titleCase(s: string | null | undefined): string {
  if (!s) return '—'
  const text = s.replace(/[_.]+/g, ' ').replace(/\s+/g, ' ').trim()
  // ALL-CAPS enums (REJECTED, TARGET_HIT) → sentence case; keep mixed-case names as-is.
  const base = text === text.toUpperCase() ? text.toLowerCase() : text
  return base.replace(/^\w/, (c) => c.toUpperCase())
}

/** NSE session in IST: pre-open 09:00–09:15, open 09:15–15:30, Mon–Fri. */
export function marketSession(now = new Date()): { label: string; open: boolean } {
  const ist = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }))
  const day = ist.getDay()
  const mins = ist.getHours() * 60 + ist.getMinutes()
  if (day === 0 || day === 6) return { label: 'Market closed · weekend', open: false }
  if (mins >= 9 * 60 && mins < 9 * 60 + 15) return { label: 'Pre-open', open: false }
  if (mins >= 9 * 60 + 15 && mins < 15 * 60 + 30) return { label: 'Market open', open: true }
  return { label: 'Market closed', open: false }
}
