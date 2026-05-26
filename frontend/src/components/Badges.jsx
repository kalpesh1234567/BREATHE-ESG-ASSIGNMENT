import React from 'react'

const STATUS_CONFIG = {
  pending:  { label: 'Pending',  cls: 'badge-pending',  dot: '●' },
  flagged:  { label: 'Flagged',  cls: 'badge-flagged',  dot: '▲' },
  approved: { label: 'Approved', cls: 'badge-approved', dot: '✓' },
  rejected: { label: 'Rejected', cls: 'badge-rejected', dot: '✗' },
  locked:   { label: 'Locked',   cls: 'badge-locked',   dot: '🔒' },
}

const SCOPE_CONFIG = {
  '1': { label: 'Scope 1', cls: 'badge-scope1' },
  '2': { label: 'Scope 2', cls: 'badge-scope2' },
  '3': { label: 'Scope 3', cls: 'badge-scope3' },
}

const SOURCE_LABELS = {
  sap_fuel: 'SAP Fuel',
  sap_procurement: 'SAP Procurement',
  utility_electricity: 'Utility',
  travel: 'Travel',
}

export function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || { label: status, cls: 'badge-pending', dot: '●' }
  return (
    <span className={`badge ${cfg.cls}`}>
      {cfg.dot} {cfg.label}
    </span>
  )
}

export function ScopeBadge({ scope }) {
  const cfg = SCOPE_CONFIG[scope] || { label: `Scope ${scope}`, cls: '' }
  return <span className={`badge ${cfg.cls}`}>{cfg.label}</span>
}

export function SourceTag({ source }) {
  return (
    <span style={{
      fontSize: 11,
      padding: '2px 7px',
      borderRadius: 4,
      background: 'var(--bg-elevated)',
      border: '1px solid var(--border)',
      color: 'var(--text-muted)',
      fontWeight: 500,
    }}>
      {SOURCE_LABELS[source] || source}
    </span>
  )
}

export function Co2eValue({ value }) {
  if (value === null || value === undefined) return <span className="text-muted">—</span>
  const num = parseFloat(value)
  const display = num >= 1000
    ? `${(num / 1000).toFixed(2)} tCO₂e`
    : `${num.toFixed(2)} kgCO₂e`
  return (
    <span className="text-mono" style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
      {display}
    </span>
  )
}
