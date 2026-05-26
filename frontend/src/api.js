import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_URL || ''

const client = axios.create({
  baseURL: `${API_BASE}/api`,
  headers: { 'Content-Type': 'application/json' },
})

// Attach JWT token to every request
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Auto-refresh on 401
client.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config
    if (err.response?.status === 401 && !original._retry) {
      original._retry = true
      const refresh = localStorage.getItem('refresh_token')
      if (refresh) {
        try {
          const { data } = await axios.post(`${API_BASE}/api/auth/refresh/`, { refresh })
          localStorage.setItem('access_token', data.access)
          client.defaults.headers.common.Authorization = `Bearer ${data.access}`
          return client(original)
        } catch {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          window.location.href = '/login'
        }
      }
    }
    return Promise.reject(err)
  }
)

export default client

export const login = (username, password) =>
  client.post('/auth/login/', { username, password })

export const getMe = () => client.get('/me/')

export const getStats = () => client.get('/stats/')

export const getRuns = (params) => client.get('/ingestion/runs/', { params })

export const uploadFile = (file, source_type) => {
  const form = new FormData()
  form.append('file', file)
  form.append('source_type', source_type)
  return client.post('/ingestion/upload/', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export const getActivities = (params) => client.get('/activities/', { params })

export const getActivity = (id) => client.get(`/activities/${id}/`)

export const editActivity = (id, data) => client.patch(`/activities/${id}/`, data)

export const approveActivity = (id) => client.post(`/activities/${id}/approve/`)

export const rejectActivity = (id, reason) =>
  client.post(`/activities/${id}/reject/`, { reason })

export const lockActivity = (id) => client.post(`/activities/${id}/lock/`)

export const bulkApprove = (ids) => client.post('/activities/bulk-approve/', { ids })

export const getAuditLog = (params) => client.get('/audit/', { params })
