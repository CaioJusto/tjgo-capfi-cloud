import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'https://backend-production-8a40.up.railway.app'

export const api = axios.create({ baseURL: API_URL })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.reload()
    }
    return Promise.reject(err)
  }
)

// Auth — login usa form-encoded (OAuth2PasswordRequestForm)
export const login = (username: string, password: string) => {
  const params = new URLSearchParams()
  params.append('username', username)
  params.append('password', password)
  return api.post('/auth/login', params, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
  }).then(r => r.data)
}

export const getMe = () => api.get('/auth/me').then(r => r.data)

// Credenciais PROJUDI
export const getCredentials = () => api.get('/credentials').then(r => r.data)
export const saveCredentials = (projudi_username: string, projudi_password: string) =>
  api.post('/credentials', { projudi_username, projudi_password }).then(r => r.data)

// Jobs
export const createJob = (data: any) => api.post('/jobs', data).then(r => r.data)
export const getJobs = (page = 1) => api.get(`/jobs?page=${page}`).then(r => r.data)
export const getJob = (id: number) => api.get(`/jobs/${id}`).then(r => r.data)
export const deleteJob = (id: number) => api.delete(`/jobs/${id}`).then(r => r.data)
export const downloadResults = (id: number) =>
  api.get(`/jobs/${id}/download`, { responseType: 'blob' }).then(r => r.data)

// Upload
export const uploadPlanilha = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return api.post('/upload/planilha', form).then(r => r.data)
}
