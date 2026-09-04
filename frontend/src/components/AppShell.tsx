import { NavLink, Outlet } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { getHealth } from '../lib/api'

const NAV_ITEMS = [
  { to: '/', label: 'Library', end: true },
  { to: '/voices', label: 'Voices' },
  { to: '/settings', label: 'Settings' },
]

function navLinkClass(isActive: boolean) {
  return [
    'block rounded-md px-3 py-2 text-sm transition-colors',
    isActive
      ? 'bg-elevated text-text'
      : 'text-text-2 hover:text-text hover:bg-elevated/60',
  ].join(' ')
}

function HealthDot() {
  const [ok, setOk] = useState<boolean | null>(null)

  useEffect(() => {
    let cancelled = false
    getHealth()
      .then(() => !cancelled && setOk(true))
      .catch(() => !cancelled && setOk(false))
    return () => {
      cancelled = true
    }
  }, [])

  const color =
    ok === null ? 'bg-text-3' : ok ? 'bg-accent' : 'bg-danger'
  const label =
    ok === null ? 'checking API…' : ok ? 'API connected' : 'API unreachable'

  return (
    <div className="flex items-center gap-2 px-3 py-2 text-xs text-text-3">
      <span className={`h-1.5 w-1.5 rounded-full ${color}`} />
      <span className="font-mono">{label}</span>
    </div>
  )
}

export default function AppShell() {
  return (
    <div className="flex h-full">
      <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-surface">
        <div className="px-4 py-5">
          <h1 className="text-sm font-semibold tracking-wide text-text">
            Audiobook <span className="text-accent">Studio</span>
          </h1>
        </div>
        <nav className="flex-1 space-y-1 px-2">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => navLinkClass(isActive)}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-border">
          <HealthDot />
        </div>
      </aside>
      <main className="flex-1 overflow-auto bg-bg">
        <Outlet />
      </main>
    </div>
  )
}
