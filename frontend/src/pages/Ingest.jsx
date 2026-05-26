import React, { useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { uploadFile, getRuns } from '../api'
import { format } from 'date-fns'
import { useToast } from '../toast'

const SOURCE_TYPES = [
  {
    id: 'sap_fuel',
    label: 'SAP — Fuel Consumption',
    icon: '⛽',
    desc: 'MB51 export: semicolon-delimited CSV, German or English headers',
    scope: 'Scope 1',
    scopeColor: 'var(--scope1)',
    accept: '.csv,.xlsx,.xls,.txt',
    detail: 'Handles Buchungsdatum (DD.MM.YYYY), Menge with European decimals (1.250,00), movement types 201/261',
  },
  {
    id: 'utility_electricity',
    label: 'Utility — Electricity',
    icon: '⚡',
    desc: 'Portal billing CSV: kWh/MWh, billing period, meter ID',
    scope: 'Scope 2',
    scopeColor: 'var(--scope2)',
    accept: '.csv',
    detail: 'Billing periods need not align with calendar months. Multiple meters per upload.',
  },
  {
    id: 'travel',
    label: 'Corporate Travel (Concur)',
    icon: '✈',
    desc: 'Standard Concur expense export: flights, hotels, ground transport',
    scope: 'Scope 3',
    scopeColor: 'var(--scope3)',
    accept: '.csv',
    detail: 'Extracts IATA codes from description, computes Great Circle distance + 9% routing uplift.',
  },
]

function UploadZone({ source, onSuccess }) {
  const [file, setFile] = useState(null)
  const [result, setResult] = useState(null)
  const toast = useToast()
  const qc = useQueryClient()

  const mutation = useMutation({
    mutationFn: (f) => uploadFile(f, source.id),
    onSuccess: (data) => {
      setResult({ type: 'success', data: data.data })
      setFile(null)
      qc.invalidateQueries(['runs'])
      qc.invalidateQueries(['stats'])
      toast(`Ingested ${data.data.parsed_count} records from ${data.data.filename}`)
      onSuccess?.()
    },
    onError: (err) => {
      const msg = err.response?.data?.error || 'Upload failed'
      setResult({ type: 'error', message: msg })
      toast(msg, 'error')
    },
  })

  const onDrop = useCallback((accepted) => {
    if (accepted[0]) setFile(accepted[0])
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: source.accept.split(',').reduce((acc, ext) => {
      const mime = ext === '.csv' ? { 'text/csv': [ext] }
        : ext === '.xlsx' ? { 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': [ext] }
        : ext === '.xls'  ? { 'application/vnd.ms-excel': [ext] }
        : { 'text/plain': [ext] }
      return { ...acc, ...mime }
    }, {}),
    maxFiles: 1,
    maxSize: 10 * 1024 * 1024,
  })

  return (
    <div className="card">
      <div className="card-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 22 }}>{source.icon}</span>
          <div>
            <div className="card-title">{source.label}</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 1 }}>{source.desc}</div>
          </div>
        </div>
        <span style={{
          fontSize: 11,
          fontWeight: 600,
          color: source.scopeColor,
          padding: '3px 9px',
          border: `1px solid ${source.scopeColor}40`,
          borderRadius: 99,
          background: `${source.scopeColor}15`,
        }}>
          {source.scope}
        </span>
      </div>

      <div className="card-body">
        <div style={{
          fontSize: 12,
          color: 'var(--text-muted)',
          marginBottom: 14,
          padding: '8px 12px',
          background: 'var(--bg-input)',
          borderRadius: 'var(--radius-sm)',
          lineHeight: 1.6,
        }}>
          ℹ {source.detail}
        </div>

        <div
          {...getRootProps()}
          className={`dropzone${isDragActive ? ' active' : ''}`}
          style={{ padding: 32 }}
        >
          <input {...getInputProps()} id={`upload-${source.id}`} />
          <div className="dropzone-icon">
            {file ? '📄' : isDragActive ? '📂' : '↑'}
          </div>
          {file ? (
            <div>
              <div className="dropzone-title" style={{ color: 'var(--green-400)' }}>
                {file.name}
              </div>
              <div className="dropzone-sub">
                {(file.size / 1024).toFixed(1)} KB · Click to change
              </div>
            </div>
          ) : (
            <div>
              <div className="dropzone-title">
                {isDragActive ? 'Drop file here' : 'Drag & drop or click to upload'}
              </div>
              <div className="dropzone-sub">Accepts: {source.accept} · Max 10 MB</div>
            </div>
          )}
        </div>

        {file && (
          <button
            id={`upload-btn-${source.id}`}
            className="btn btn-primary"
            style={{ marginTop: 12, width: '100%', justifyContent: 'center' }}
            onClick={() => mutation.mutate(file)}
            disabled={mutation.isPending}
          >
            {mutation.isPending
              ? <><span className="spinner" style={{ width: 16, height: 16 }} /> Processing…</>
              : `Ingest ${source.label}`
            }
          </button>
        )}

        {result && (
          <div className={`upload-result ${result.type}`}>
            {result.type === 'success' ? (
              <div>
                <strong>✓ Ingested successfully</strong>
                <div style={{ marginTop: 4, fontSize: 12 }}>
                  {result.data.parsed_count} records parsed
                  {result.data.error_count > 0 && (
                    <span style={{ color: 'var(--amber-500)' }}>
                      {' '}· {result.data.error_count} rows skipped
                    </span>
                  )}
                </div>
              </div>
            ) : (
              <div>
                <strong>✗ Upload failed</strong>
                <div style={{ marginTop: 4, fontSize: 12 }}>{result.message}</div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function RunHistory() {
  const { data, isLoading } = useQuery({
    queryKey: ['runs'],
    queryFn: () => getRuns().then(r => r.data),
    refetchInterval: 15000,
  })

  const SOURCE_LABELS = {
    sap_fuel: 'SAP Fuel',
    sap_procurement: 'SAP Procurement',
    utility_electricity: 'Utility',
    travel: 'Travel',
  }

  const STATUS_COLOR = {
    complete: 'var(--green-400)',
    processing: 'var(--amber-500)',
    failed: 'var(--red-500)',
  }

  if (isLoading) return (
    <div className="loading-state" style={{ padding: 32 }}>
      <div className="spinner" />
    </div>
  )

  const runs = data?.results || data || []

  if (!runs.length) return (
    <div className="empty-state">
      <div className="empty-icon">📂</div>
      <div className="empty-title">No uploads yet</div>
      <div className="empty-sub">Upload files above to start ingesting data</div>
    </div>
  )

  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="data-table">
        <thead>
          <tr>
            <th>File</th>
            <th>Source</th>
            <th>Status</th>
            <th>Records</th>
            <th>Errors</th>
            <th>Uploaded</th>
          </tr>
        </thead>
        <tbody>
          {runs.map(run => (
            <tr key={run.id}>
              <td className="td-primary" style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {run.filename}
              </td>
              <td>{SOURCE_LABELS[run.source_type] || run.source_type}</td>
              <td>
                <span style={{
                  color: STATUS_COLOR[run.status] || 'var(--text-muted)',
                  fontWeight: 600,
                  fontSize: 12,
                }}>
                  ● {run.status}
                </span>
              </td>
              <td className="td-mono">{run.parsed_count}</td>
              <td className="td-mono" style={{ color: run.error_count > 0 ? 'var(--amber-500)' : 'inherit' }}>
                {run.error_count}
              </td>
              <td className="td-muted">
                {run.uploaded_at ? format(new Date(run.uploaded_at), 'MMM d, HH:mm') : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function Ingest() {
  const [key, setKey] = useState(0)

  return (
    <div className="page-container">
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.5px' }}>
          Ingest Data
        </h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>
          Upload source files for parsing, normalization, and CO₂e calculation
        </p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 20, marginBottom: 32 }}>
        {SOURCE_TYPES.map(source => (
          <UploadZone key={`${source.id}-${key}`} source={source} onSuccess={() => setKey(k => k + 1)} />
        ))}
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Ingestion History</span>
        </div>
        <RunHistory />
      </div>
    </div>
  )
}
