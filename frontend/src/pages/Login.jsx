import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ username: '', password: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      await login(form.username, form.password)
      navigate('/')
    } catch (err) {
      setError(err.response?.data?.detail || 'Invalid credentials. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-glow" style={{ top: '-100px', left: '50%', transform: 'translateX(-50%)' }} />
      <div className="login-card">
        <div className="login-logo">
          <div className="login-logo-icon">🌿</div>
          <div className="login-title">BreatheESG</div>
          <div className="login-sub">Emissions Intelligence Platform</div>
        </div>

        <form onSubmit={handleSubmit}>
          {error && <div className="login-error">{error}</div>}

          <div className="form-group">
            <label className="form-label" htmlFor="username">Username</label>
            <input
              id="username"
              type="text"
              className="form-input"
              placeholder="admin or analyst"
              value={form.username}
              onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
              required
              autoFocus
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              className="form-input"
              placeholder="breatheesg2024"
              value={form.password}
              onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
              required
            />
          </div>

          <button
            type="submit"
            id="login-btn"
            className="btn btn-primary btn-lg"
            style={{ width: '100%', marginTop: 8, justifyContent: 'center' }}
            disabled={loading}
          >
            {loading ? <span className="spinner" style={{ width: 18, height: 18 }} /> : null}
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        <div style={{
          marginTop: 28,
          padding: 16,
          background: 'var(--bg-input)',
          borderRadius: 'var(--radius-md)',
          border: '1px solid var(--border)',
        }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.8px', fontWeight: 600 }}>
            Demo Credentials
          </div>
          {[
            { user: 'admin', pass: 'breatheesg2024', role: 'Admin — can lock records' },
            { user: 'analyst', pass: 'breatheesg2024', role: 'Analyst — review & approve' },
          ].map(c => (
            <div
              key={c.user}
              onClick={() => setForm({ username: c.user, password: c.pass })}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '6px 8px',
                cursor: 'pointer',
                borderRadius: 6,
                marginBottom: 4,
                transition: 'background 0.1s',
              }}
              onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-hover)'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              <div>
                <div style={{ fontSize: 12.5, color: 'var(--text-primary)', fontWeight: 600 }}>{c.user}</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{c.role}</div>
              </div>
              <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'monospace' }}>click to fill</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
