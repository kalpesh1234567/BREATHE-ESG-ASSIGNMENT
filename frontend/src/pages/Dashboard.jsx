import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { getStats } from '../api'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts'

const COLORS = {
  scope_1: '#f97316',
  scope_2: '#3b82f6',
  scope_3: '#a855f7',
}

const SOURCE_LABELS = {
  sap_fuel: 'SAP Fuel',
  sap_procurement: 'SAP Procurement',
  utility_electricity: 'Utility',
  travel: 'Travel',
}

function StatCard({ label, value, unit, variant = 'default', subtitle }) {
  return (
    <div className={`stat-card ${variant}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {unit && <div className="stat-unit">{unit}</div>}
      {subtitle && <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>{subtitle}</div>}
    </div>
  )
}

const CustomTooltip = ({ active, payload }) => {
  if (active && payload?.[0]) {
    const { name, value } = payload[0]
    return (
      <div style={{
        background: 'var(--bg-elevated)',
        border: '1px solid var(--border)',
        borderRadius: 8,
        padding: '8px 12px',
        fontSize: 12,
        color: 'var(--text-primary)',
      }}>
        <div style={{ fontWeight: 600 }}>{name}</div>
        <div>{typeof value === 'number' ? `${(value / 1000).toFixed(2)} tCO₂e` : value}</div>
      </div>
    )
  }
  return null
}

export default function Dashboard() {
  const { data: stats, isLoading } = useQuery({
    queryKey: ['stats'],
    queryFn: () => getStats().then(r => r.data),
    refetchInterval: 60000,
  })

  if (isLoading || !stats) {
    return (
      <div className="page-container">
        <div className="loading-state">
          <div className="spinner" />
          <span>Loading dashboard...</span>
        </div>
      </div>
    )
  }

  const totalCo2e = stats.total_co2e_kg || 0
  const scopeData = [
    { name: 'Scope 1', value: stats.scope_breakdown?.scope_1?.co2e_kg || 0 },
    { name: 'Scope 2', value: stats.scope_breakdown?.scope_2?.co2e_kg || 0 },
    { name: 'Scope 3', value: stats.scope_breakdown?.scope_3?.co2e_kg || 0 },
  ]

  const sourceData = (stats.source_breakdown || []).map(s => ({
    name: SOURCE_LABELS[s.source_type] || s.source_type,
    value: parseFloat(s.co2e || 0),
  }))

  return (
    <div className="page-container">
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.5px', color: 'var(--text-primary)' }}>
          Emissions Dashboard
        </h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>
          ACME Manufacturing GmbH · 2024 Reporting Period
        </p>
      </div>

      {/* Summary Stats */}
      <div className="stat-grid">
        <StatCard
          label="Total CO₂e"
          value={(totalCo2e / 1000).toFixed(1)}
          unit="tonnes CO₂e"
          variant="success"
          subtitle="All scopes combined"
        />
        <StatCard
          label="Pending Review"
          value={stats.pending}
          unit="records"
          variant={stats.pending > 0 ? 'warning' : 'default'}
          subtitle="Awaiting analyst action"
        />
        <StatCard
          label="Flagged"
          value={stats.flagged}
          unit="records"
          variant={stats.flagged > 0 ? 'danger' : 'default'}
          subtitle="Suspicious or missing data"
        />
        <StatCard
          label="Approved"
          value={stats.approved}
          unit="records"
          variant="info"
          subtitle="Ready to lock"
        />
        <StatCard
          label="Locked"
          value={stats.locked}
          unit="records"
          subtitle="Audit-ready"
        />
        <StatCard
          label="Total Records"
          value={stats.total_records}
          unit="activity records"
          subtitle="Across all sources"
        />
      </div>

      {/* Charts row */}
      <div className="grid-2" style={{ gap: 20, marginBottom: 24 }}>
        {/* Scope Breakdown Donut */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Scope Breakdown</span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>By GHG Protocol scope</span>
          </div>
          <div className="card-body">
            <div className="chart-container">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={scopeData}
                    cx="40%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={90}
                    paddingAngle={3}
                    dataKey="value"
                  >
                    {scopeData.map((_, i) => (
                      <Cell
                        key={i}
                        fill={Object.values(COLORS)[i]}
                        stroke="transparent"
                      />
                    ))}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                  <Legend
                    formatter={(value, entry) => (
                      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                        {value}
                      </span>
                    )}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            {/* Scope detail rows */}
            {[
              { key: 'scope_1', label: 'Scope 1 — Direct (Fuel)', color: COLORS.scope_1, desc: 'SAP MB51 fuel consumption' },
              { key: 'scope_2', label: 'Scope 2 — Electricity', color: COLORS.scope_2, desc: 'Utility portal billing data' },
              { key: 'scope_3', label: 'Scope 3 — Travel', color: COLORS.scope_3, desc: 'Concur corporate travel' },
            ].map(s => {
              const co2e = stats.scope_breakdown?.[s.key]?.co2e_kg || 0
              const pct = totalCo2e > 0 ? (co2e / totalCo2e * 100).toFixed(1) : '0'
              return (
                <div key={s.key} style={{ marginBottom: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span style={{ fontSize: 12, color: s.color, fontWeight: 600 }}>{s.label}</span>
                    <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      {(co2e / 1000).toFixed(2)} tCO₂e · {pct}%
                    </span>
                  </div>
                  <div style={{ height: 4, background: 'var(--border)', borderRadius: 99, overflow: 'hidden' }}>
                    <div style={{
                      height: '100%',
                      width: `${pct}%`,
                      background: s.color,
                      borderRadius: 99,
                      transition: 'width 0.6s ease',
                    }} />
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 2 }}>{s.desc}</div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Source Bar Chart */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">CO₂e by Source</span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>tonnes CO₂e</span>
          </div>
          <div className="card-body">
            <div className="chart-container" style={{ marginBottom: 16 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={sourceData} barCategoryGap="35%">
                  <XAxis
                    dataKey="name"
                    tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fill: 'var(--text-muted)', fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={v => `${(v / 1000).toFixed(0)}t`}
                  />
                  <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
                  <Bar
                    dataKey="value"
                    fill="var(--green-500)"
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Review status breakdown */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
              {[
                { label: 'Approved', count: stats.approved, color: 'var(--green-500)' },
                { label: 'Pending', count: stats.pending, color: 'var(--amber-500)' },
                { label: 'Rejected', count: stats.rejected, color: 'var(--red-500)' },
              ].map(s => (
                <div key={s.label} style={{
                  background: 'var(--bg-elevated)',
                  border: '1px solid var(--border)',
                  borderRadius: 8,
                  padding: '10px 12px',
                  textAlign: 'center',
                }}>
                  <div style={{ fontSize: 20, fontWeight: 700, color: s.color }}>{s.count}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{s.label}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Methodology note */}
      <div style={{
        padding: '14px 18px',
        background: 'rgba(59, 130, 246, 0.06)',
        border: '1px solid rgba(59, 130, 246, 0.15)',
        borderRadius: 'var(--radius-md)',
        fontSize: 12,
        color: 'var(--text-muted)',
        lineHeight: 1.7,
      }}>
        <strong style={{ color: 'var(--blue-500)' }}>Methodology:</strong>{' '}
        Scope 1 emission factors from DEFRA 2024 (combustion only / tank-to-wheel).
        Scope 2 uses location-based UK National Grid factor (0.207 kgCO₂e/kWh, DEFRA/DESNZ 2024).
        Scope 3 travel factors from DEFRA 2024, including 1.7× Radiative Forcing uplift for flights.
        Records are only included in totals after approval. Locked records are audit-ready.
      </div>
    </div>
  )
}
