import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getAuditLog } from '../api'
import { format } from 'date-fns'

const ACTION_COLORS = {
  ingested: 'var(--text-muted)',
  approved: 'var(--green-400)',
  rejected: 'var(--red-500)',
  locked: 'var(--blue-500)',
  flagged: 'var(--amber-500)',
  edited: 'var(--blue-500)',
  unflagged: 'var(--text-muted)',
}

const ACTION_ICONS = {
  ingested: '↑',
  approved: '✓',
  rejected: '✗',
  locked: '🔒',
  flagged: '⚠',
  edited: '✏',
  unflagged: '◎',
}

// Status → display label + color
const STATUS_DISPLAY = {
  pending:  { label: 'Pending',  color: 'var(--amber-500)' },
  approved: { label: 'Approved', color: 'var(--green-400)' },
  rejected: { label: 'Rejected', color: 'var(--red-500)'   },
  flagged:  { label: 'Flagged',  color: 'var(--amber-500)' },
  locked:   { label: 'Locked',   color: 'var(--blue-500)'  },
}

// Pretty-print a single key:value pair from a state snapshot
function StateField({ k, v }) {
  if (k === 'status') {
    const s = STATUS_DISPLAY[v] || { label: v, color: 'var(--text-muted)' }
    return (
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: 5,
        fontSize: 12, fontWeight: 600, color: s.color,
      }}>
        <span style={{
          width: 7, height: 7, borderRadius: '50%',
          background: s.color, display: 'inline-block', flexShrink: 0,
        }} />
        {s.label}
      </span>
    )
  }

  if (k === 'co2e_kg' && v != null) {
    const num = parseFloat(v)
    return (
      <span style={{ fontSize: 12, color: 'var(--text-primary)' }}>
        {isNaN(num) ? v : `${(num / 1000).toFixed(3)} tCO₂e`}
      </span>
    )
  }

  if (k === 'suspicion_reasons' && Array.isArray(v)) {
    return (
      <span style={{ fontSize: 11, color: 'var(--amber-500)' }}>
        {v.length} flag{v.length !== 1 ? 's' : ''}
      </span>
    )
  }

  if (k === 'category') {
    return (
      <span style={{
        fontSize: 11, color: 'var(--text-secondary)',
        background: 'var(--bg-elevated)',
        padding: '1px 6px', borderRadius: 4,
      }}>
        {String(v)}
      </span>
    )
  }

  if (v == null || v === '') return <span style={{ color: 'var(--text-dim)' }}>—</span>

  return <span style={{ fontSize: 12, color: 'var(--text-primary)' }}>{String(v)}</span>
}

// Render a state snapshot object as readable rows
function StateBlock({ state }) {
  if (!state || typeof state !== 'object') return <span style={{ color: 'var(--text-dim)' }}>—</span>

  const entries = Object.entries(state)
  if (entries.length === 0) return <span style={{ color: 'var(--text-dim)' }}>—</span>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      {entries.map(([k, v]) => (
        <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            fontSize: 10, color: 'var(--text-dim)', textTransform: 'uppercase',
            letterSpacing: '0.6px', minWidth: 54, flexShrink: 0,
          }}>
            {k.replace(/_/g, ' ')}
          </span>
          <StateField k={k} v={v} />
        </div>
      ))}
    </div>
  )
}

export default function AuditPage() {
  const [page, setPage] = useState(1)
  const [actionFilter, setActionFilter] = useState('')

  const params = {
    page,
    page_size: 50,
    ordering: '-timestamp',
    ...(actionFilter && { action: actionFilter }),
  }

  const { data, isLoading } = useQuery({
    queryKey: ['audit', params],
    queryFn: () => getAuditLog(params).then(r => r.data),
    keepPreviousData: true,
  })

  const logs = data?.results || data || []
  const total = data?.count || logs.length
  const totalPages = Math.ceil(total / 50)

  return (
    <div className="page-container">
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.5px' }}>Audit Log</h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>
          Append-only record of every state transition — {total} entries
        </p>
      </div>

      {/* Action filter */}
      <div className="filters-bar" style={{ marginBottom: 20 }}>
        {['', 'ingested', 'approved', 'rejected', 'locked', 'flagged', 'edited'].map(a => (
          <button
            key={a}
            className={`filter-chip${actionFilter === a ? ' active' : ''}`}
            onClick={() => { setActionFilter(a); setPage(1) }}
          >
            {a === '' ? 'All Actions' : (ACTION_ICONS[a] + ' ' + a.charAt(0).toUpperCase() + a.slice(1))}
          </button>
        ))}
      </div>

      <div className="card">
        {isLoading ? (
          <div className="loading-state"><div className="spinner" /></div>
        ) : logs.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">⊟</div>
            <div className="empty-title">No audit entries</div>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Action</th>
                  <th>Actor</th>
                  <th>Record</th>
                  <th>Note</th>
                  <th>Change</th>
                </tr>
              </thead>
              <tbody>
                {logs.map(log => (
                  <tr key={log.id}>
                    <td className="td-muted" style={{ whiteSpace: 'nowrap' }}>
                      {log.timestamp ? format(new Date(log.timestamp), 'MMM d, HH:mm:ss') : '—'}
                    </td>
                    <td>
                      <span style={{
                        fontSize: 12, fontWeight: 700,
                        color: ACTION_COLORS[log.action] || 'var(--text-secondary)',
                      }}>
                        {ACTION_ICONS[log.action]} {log.action_display}
                      </span>
                    </td>
                    <td className="td-primary" style={{ fontSize: 12.5 }}>{log.actor_name}</td>
                    <td className="td-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                      {String(log.record || '').slice(0, 8)}…
                    </td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)', maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {log.note || '—'}
                    </td>
                    <td style={{ minWidth: 160 }}>
                      {/* Show before → after when both exist (edits), else just after_state */}
                      {log.before_state && Object.keys(log.before_state).length > 0 ? (
                        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                          <div style={{ opacity: 0.45 }}>
                            <StateBlock state={log.before_state} />
                          </div>
                          <span style={{ fontSize: 14, color: 'var(--text-dim)', paddingTop: 1, flexShrink: 0 }}>→</span>
                          <StateBlock state={log.after_state} />
                        </div>
                      ) : (
                        <StateBlock state={log.after_state} />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {totalPages > 1 && (
          <div className="pagination">
            <div className="page-info">Page {page} of {totalPages}</div>
            <div className="page-controls">
              <button className="page-btn" onClick={() => setPage(p => p - 1)} disabled={page <= 1}>←</button>
              <button className="page-btn" onClick={() => setPage(p => p + 1)} disabled={page >= totalPages}>→</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
