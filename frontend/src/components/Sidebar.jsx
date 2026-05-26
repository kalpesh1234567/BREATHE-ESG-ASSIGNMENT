import React from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import { useQuery } from '@tanstack/react-query'
import { getStats } from '../api'

const navItems = [
  { to: '/',        icon: '⬡', label: 'Dashboard' },
  { to: '/ingest',  icon: '↑', label: 'Ingest Data' },
  { to: '/review',  icon: '◎', label: 'Review Queue', badgeKey: 'pending' },
  { to: '/audit',   icon: '⊟', label: 'Audit Log' },
]

export default function Sidebar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const { data: stats } = useQuery({
    queryKey: ['stats'],
    queryFn: () => getStats().then(r => r.data),
    refetchInterval: 30000,
  })

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const pendingCount = stats?.pending || 0
  const flaggedCount = stats?.flagged || 0
  const badge = pendingCount + flaggedCount

  const initials = user
    ? (user.full_name || user.username).split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()
    : '??'

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="logo-mark">
          <div className="logo-icon">🌿</div>
          <div>
            <div className="logo-text">BreatheESG</div>
            <div className="logo-sub">Emissions Intelligence</div>
          </div>
        </div>
      </div>

      <nav className="sidebar-nav">
        <div className="nav-section-label">Platform</div>
        {navItems.map(item => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
          >
            <span className="nav-icon">{item.icon}</span>
            {item.label}
            {item.badgeKey && badge > 0 && (
              <span className="nav-badge">{badge > 99 ? '99+' : badge}</span>
            )}
          </NavLink>
        ))}

        {stats && (
          <>
            <div className="nav-section-label" style={{ marginTop: 16 }}>This Period</div>
            <div style={{ padding: '8px 12px' }}>
              {[
                { label: 'Scope 1', value: stats.scope_breakdown?.scope_1?.co2e_kg, color: 'var(--scope1)' },
                { label: 'Scope 2', value: stats.scope_breakdown?.scope_2?.co2e_kg, color: 'var(--scope2)' },
                { label: 'Scope 3', value: stats.scope_breakdown?.scope_3?.co2e_kg, color: 'var(--scope3)' },
              ].map(s => (
                <div key={s.label} style={{ marginBottom: 6 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 3 }}>
                    <span style={{ color: s.color, fontWeight: 600 }}>{s.label}</span>
                    <span style={{ color: 'var(--text-muted)' }}>
                      {s.value ? `${(s.value / 1000).toFixed(1)} tCO₂e` : '—'}
                    </span>
                  </div>
                  <div style={{
                    height: 3,
                    background: 'var(--border)',
                    borderRadius: 99,
                    overflow: 'hidden',
                  }}>
                    <div style={{
                      height: '100%',
                      width: `${Math.min(100, ((s.value || 0) / Math.max(1, stats.total_co2e_kg || 1)) * 100)}%`,
                      background: s.color,
                      borderRadius: 99,
                      transition: 'width 0.5s ease',
                    }} />
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </nav>

      <div className="sidebar-footer">
        <div className="user-block" onClick={handleLogout} title="Click to log out">
          <div className="user-avatar">{initials}</div>
          <div className="user-info">
            <div className="user-name">{user?.full_name || user?.username}</div>
            <div className="user-role">{user?.role} · {user?.organization?.name}</div>
          </div>
          <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>→</span>
        </div>
      </div>
    </aside>
  )
}
