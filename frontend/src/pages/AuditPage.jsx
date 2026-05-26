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
                  <th>Before → After</th>
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
                        fontSize: 12,
                        fontWeight: 700,
                        color: ACTION_COLORS[log.action] || 'var(--text-secondary)',
                      }}>
                        {ACTION_ICONS[log.action]} {log.action_display}
                      </span>
                    </td>
                    <td className="td-primary" style={{ fontSize: 12.5 }}>{log.actor_name}</td>
                    <td className="td-mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                      {String(log.record || '').slice(0, 8)}…
                    </td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {log.note || '—'}
                    </td>
                    <td>
                      {log.after_state && (
                        <span style={{
                          fontSize: 11,
                          fontFamily: 'monospace',
                          color: 'var(--text-muted)',
                          background: 'var(--bg-elevated)',
                          padding: '2px 6px',
                          borderRadius: 4,
                          maxWidth: 200,
                          display: 'inline-block',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          verticalAlign: 'middle',
                        }}>
                          {JSON.stringify(log.after_state).slice(0, 60)}
                        </span>
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
