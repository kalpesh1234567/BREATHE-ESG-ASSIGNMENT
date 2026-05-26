import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getActivities, getActivity, approveActivity, rejectActivity, lockActivity, bulkApprove } from '../api'
import { StatusBadge, ScopeBadge, SourceTag, Co2eValue } from '../components/Badges'
import { format } from 'date-fns'
import { useToast } from '../toast'
import { useAuth } from '../auth'

// ── Filter configuration ──────────────────────────────────────────────────────
const STATUS_FILTERS = [
  { key: '', label: 'All' },
  { key: 'pending', label: 'Pending' },
  { key: 'flagged', label: 'Flagged' },
  { key: 'approved', label: 'Approved' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'locked', label: 'Locked' },
]

const SCOPE_FILTERS = [
  { key: '', label: 'All Scopes' },
  { key: '1', label: 'Scope 1' },
  { key: '2', label: 'Scope 2' },
  { key: '3', label: 'Scope 3' },
]

// ── Detail Panel ──────────────────────────────────────────────────────────────
function DetailPanel({ id, onClose }) {
  const { user } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const [rejectReason, setRejectReason] = useState('')
  const [showRejectInput, setShowRejectInput] = useState(false)

  const { data: record, isLoading } = useQuery({
    queryKey: ['activity', id],
    queryFn: () => getActivity(id).then(r => r.data),
    enabled: !!id,
  })

  const invalidate = () => {
    qc.invalidateQueries(['activities'])
    qc.invalidateQueries(['activity', id])
    qc.invalidateQueries(['stats'])
  }

  const approveMut = useMutation({
    mutationFn: () => approveActivity(id),
    onSuccess: () => { toast('Record approved'); invalidate() },
    onError: (e) => toast(e.response?.data?.error || 'Approve failed', 'error'),
  })

  const rejectMut = useMutation({
    mutationFn: () => rejectActivity(id, rejectReason),
    onSuccess: () => { toast('Record rejected'); setShowRejectInput(false); invalidate() },
    onError: (e) => toast(e.response?.data?.error || 'Reject failed', 'error'),
  })

  const lockMut = useMutation({
    mutationFn: () => lockActivity(id),
    onSuccess: () => { toast('Record locked for audit'); invalidate() },
    onError: (e) => toast(e.response?.data?.error || 'Lock failed', 'error'),
  })

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="detail-panel" onClick={e => e.stopPropagation()}>
        <div className="panel-header">
          <div>
            <div style={{ fontSize: 14, fontWeight: 600 }}>Record Detail</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
              {id?.slice(0, 8)}…
            </div>
          </div>
          <button className="btn btn-secondary btn-sm btn-icon" onClick={onClose}>✕</button>
        </div>

        <div className="panel-body">
          {isLoading && (
            <div className="loading-state">
              <div className="spinner" />
            </div>
          )}

          {record && (
            <>
              {/* Suspicious banner */}
              {record.is_suspicious && (
                <div className="suspicious-banner">
                  <span className="suspicious-banner-icon">⚠</span>
                  <div className="suspicious-banner-text">
                    <strong>Auto-flagged during ingestion:</strong>
                    <ul style={{ marginTop: 4, paddingLeft: 14 }}>
                      {(record.suspicion_reasons || []).map((r, i) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              {/* Classification */}
              <div style={{ display: 'flex', gap: 8, marginBottom: 20, flexWrap: 'wrap' }}>
                <StatusBadge status={record.status} />
                <ScopeBadge scope={record.scope} />
                <SourceTag source={record.source_type} />
              </div>

              {/* Key values */}
              <div className="grid-2" style={{ marginBottom: 20 }}>
                {[
                  { label: 'Category', value: record.category },
                  { label: 'Period', value: `${record.period_start} → ${record.period_end}` },
                  { label: 'Facility', value: record.facility_code || '—' },
                  { label: 'CO₂e', value: null, co2e: record.co2e_kg },
                  { label: 'Raw Quantity', value: `${parseFloat(record.quantity_raw).toLocaleString()} ${record.unit_raw}` },
                  { label: 'Normalized', value: `${parseFloat(record.quantity_normalized).toLocaleString()} ${record.unit_normalized}` },
                  { label: 'Emission Factor', value: record.emission_factor_value ? `${record.emission_factor_value} kgCO₂e/${record.emission_factor_unit}` : '—' },
                  { label: 'Ingestion Run', value: record.ingestion_run?.filename },
                ].map(item => (
                  <div key={item.label} style={{
                    padding: '10px 12px',
                    background: 'var(--bg-base)',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border)',
                  }}>
                    <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.7px', color: 'var(--text-muted)', fontWeight: 600, marginBottom: 4 }}>
                      {item.label}
                    </div>
                    <div style={{ fontSize: 13, color: 'var(--text-primary)', wordBreak: 'break-all' }}>
                      {item.co2e !== undefined ? <Co2eValue value={item.co2e} /> : (item.value || '—')}
                    </div>
                  </div>
                ))}
              </div>

              {/* Edit badge */}
              {record.is_edited && (
                <div style={{
                  padding: '8px 12px',
                  background: 'rgba(59, 130, 246, 0.08)',
                  border: '1px solid rgba(59, 130, 246, 0.2)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: 12,
                  color: 'var(--blue-500)',
                  marginBottom: 16,
                }}>
                  ✏ Edited by analyst — original values preserved
                </div>
              )}

              {/* Raw data */}
              <div className="section-heading" style={{ marginBottom: 8 }}>Raw Source Data</div>
              <div className="raw-data" style={{ marginBottom: 20 }}>
                {Object.entries(record.raw_data || {}).map(([k, v]) => (
                  <div key={k} className="raw-data-row">
                    <span className="raw-data-key">{k}</span>
                    <span className="raw-data-val">{v || '—'}</span>
                  </div>
                ))}
              </div>

              {/* Audit trail */}
              <div className="section-heading" style={{ marginBottom: 12 }}>Audit Trail</div>
              <div className="audit-timeline">
                {(record.audit_logs || []).map(log => (
                  <div key={log.id} className={`audit-item action-${log.action}`}>
                    <div className="audit-action">
                      {log.action_display}
                      {log.note && <span style={{ fontWeight: 400, color: 'var(--text-secondary)' }}> — {log.note}</span>}
                    </div>
                    <div className="audit-meta">
                      {log.actor_name} · {log.timestamp ? format(new Date(log.timestamp), 'MMM d, yyyy HH:mm') : ''}
                    </div>
                  </div>
                ))}
              </div>

              {/* Reject reason input */}
              {showRejectInput && (
                <div style={{ marginTop: 16 }}>
                  <textarea
                    className="form-input"
                    rows={3}
                    placeholder="Reason for rejection (required for audit trail)"
                    value={rejectReason}
                    onChange={e => setRejectReason(e.target.value)}
                    style={{ resize: 'vertical' }}
                  />
                  <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                    <button
                      id="confirm-reject-btn"
                      className="btn btn-danger"
                      onClick={() => rejectMut.mutate()}
                      disabled={!rejectReason.trim() || rejectMut.isPending}
                    >
                      Confirm Reject
                    </button>
                    <button className="btn btn-secondary" onClick={() => setShowRejectInput(false)}>
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {record && !record.is_locked && (
          <div className="panel-footer">
            {record.status !== 'approved' && record.status !== 'locked' && (
              <button
                id="approve-btn"
                className="btn btn-success"
                onClick={() => approveMut.mutate()}
                disabled={approveMut.isPending}
              >
                ✓ Approve
              </button>
            )}
            {record.status !== 'rejected' && record.status !== 'locked' && (
              <button
                id="reject-btn"
                className="btn btn-danger"
                onClick={() => setShowRejectInput(true)}
              >
                ✗ Reject
              </button>
            )}
            {record.status === 'approved' && user?.role === 'admin' && (
              <button
                id="lock-btn"
                className="btn btn-secondary"
                onClick={() => lockMut.mutate()}
                disabled={lockMut.isPending}
              >
                🔒 Lock for Audit
              </button>
            )}
            <button className="btn btn-secondary" style={{ marginLeft: 'auto' }} onClick={onClose}>
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main Review Table ─────────────────────────────────────────────────────────
export default function Review() {
  const [filters, setFilters] = useState({ status: 'pending', scope: '', page: 1 })
  const [selected, setSelected] = useState(new Set())
  const [detailId, setDetailId] = useState(null)
  const toast = useToast()
  const qc = useQueryClient()

  const params = {
    ...(filters.status && { status: filters.status }),
    ...(filters.scope && { scope: filters.scope }),
    page: filters.page,
    page_size: 50,
    ordering: '-period_start',
  }

  const { data, isLoading } = useQuery({
    queryKey: ['activities', params],
    queryFn: () => getActivities(params).then(r => r.data),
    keepPreviousData: true,
    refetchInterval: 30000,
  })

  const bulkMut = useMutation({
    mutationFn: () => bulkApprove([...selected]),
    onSuccess: (data) => {
      toast(`${data.data.approved} records approved`)
      setSelected(new Set())
      qc.invalidateQueries(['activities'])
      qc.invalidateQueries(['stats'])
    },
    onError: (e) => toast(e.response?.data?.error || 'Bulk approve failed', 'error'),
  })

  const records = data?.results || data || []
  const total = data?.count || records.length
  const totalPages = Math.ceil(total / 50)

  const toggleSelect = (id) => {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    if (selected.size === records.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(records.map(r => r.id)))
    }
  }

  return (
    <div className="page-container" style={{ paddingBottom: 0 }}>
      {detailId && (
        <DetailPanel id={detailId} onClose={() => setDetailId(null)} />
      )}

      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.5px' }}>Review Queue</h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>
          {total} records · {selected.size} selected
        </p>
      </div>

      {/* Filters */}
      <div className="filters-bar">
        <div style={{ display: 'flex', gap: 6 }}>
          {STATUS_FILTERS.map(f => (
            <button
              key={f.key}
              className={`filter-chip${filters.status === f.key ? ' active' : ''}`}
              onClick={() => setFilters(p => ({ ...p, status: f.key, page: 1 }))}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          <select
            className="form-input form-select"
            style={{ width: 130, padding: '6px 32px 6px 10px' }}
            value={filters.scope}
            onChange={e => setFilters(p => ({ ...p, scope: e.target.value, page: 1 }))}
          >
            {SCOPE_FILTERS.map(f => (
              <option key={f.key} value={f.key}>{f.label}</option>
            ))}
          </select>

          {selected.size > 0 && (
            <button
              id="bulk-approve-btn"
              className="btn btn-success"
              onClick={() => bulkMut.mutate()}
              disabled={bulkMut.isPending}
            >
              ✓ Approve {selected.size} selected
            </button>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="card" style={{ borderRadius: '16px 16px 0 0' }}>
        {isLoading ? (
          <div className="loading-state">
            <div className="spinner" />
          </div>
        ) : records.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">◎</div>
            <div className="empty-title">Queue is clear</div>
            <div className="empty-sub">No records match the current filters</div>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ width: 36 }}>
                    <input
                      type="checkbox"
                      checked={selected.size === records.length && records.length > 0}
                      onChange={toggleAll}
                      style={{ cursor: 'pointer', accentColor: 'var(--green-500)' }}
                    />
                  </th>
                  <th>Category</th>
                  <th>Scope</th>
                  <th>Period</th>
                  <th>Facility</th>
                  <th>CO₂e</th>
                  <th>Status</th>
                  <th>Flags</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {records.map(rec => (
                  <tr
                    key={rec.id}
                    className={`${selected.has(rec.id) ? 'selected' : ''}${rec.is_suspicious ? ' suspicious-row' : ''}`}
                    onClick={() => setDetailId(rec.id)}
                  >
                    <td onClick={e => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selected.has(rec.id)}
                        onChange={() => toggleSelect(rec.id)}
                        style={{ cursor: 'pointer', accentColor: 'var(--green-500)' }}
                      />
                    </td>
                    <td>
                      <div className="td-primary" style={{ fontSize: 12.5, fontWeight: 600 }}>
                        {rec.category}
                      </div>
                      <div style={{ marginTop: 3 }}>
                        <SourceTag source={rec.source_type} />
                      </div>
                    </td>
                    <td><ScopeBadge scope={rec.scope} /></td>
                    <td className="td-muted">
                      {rec.period_start}
                      {rec.period_start !== rec.period_end && (
                        <div style={{ fontSize: 10 }}>→ {rec.period_end}</div>
                      )}
                    </td>
                    <td className="td-muted" style={{ maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {rec.facility_code || '—'}
                    </td>
                    <td><Co2eValue value={rec.co2e_kg} /></td>
                    <td><StatusBadge status={rec.status} /></td>
                    <td>
                      {rec.is_suspicious && (
                        <span title={rec.suspicion_reasons?.join('; ')} style={{ color: 'var(--amber-500)', fontSize: 14 }}>
                          ⚠
                        </span>
                      )}
                      {rec.is_edited && (
                        <span title="Edited by analyst" style={{ color: 'var(--blue-500)', fontSize: 12, marginLeft: 4 }}>
                          ✏
                        </span>
                      )}
                    </td>
                    <td>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={e => { e.stopPropagation(); setDetailId(rec.id) }}
                      >
                        View →
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="pagination" style={{ background: 'var(--bg-card)', borderRadius: '0 0 16px 16px', border: '1px solid var(--border)', borderTop: 'none' }}>
          <div className="page-info">
            Page {filters.page} of {totalPages} · {total} records
          </div>
          <div className="page-controls">
            <button
              className="page-btn"
              onClick={() => setFilters(p => ({ ...p, page: p.page - 1 }))}
              disabled={filters.page <= 1}
            >←</button>
            <button
              className="page-btn"
              onClick={() => setFilters(p => ({ ...p, page: p.page + 1 }))}
              disabled={filters.page >= totalPages}
            >→</button>
          </div>
        </div>
      )}
    </div>
  )
}
