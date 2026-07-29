import axios from 'axios'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL
  || (import.meta.env.DEV ? 'http://127.0.0.1:8012/api/v1' : '/api/v1')

const api = axios.create({ baseURL: API_BASE_URL, timeout: 30000 })

export const getClients = () => api.get('/clients').then(({ data }) => data)
export const getCampaigns = (clientId) => api.get(`/clients/${clientId}/campaigns`).then(({ data }) => data)
export const createClient = (payload) => api.post('/clients', payload).then(({ data }) => data)
export const syncClient = (clientId, params) => api.post(`/clients/${clientId}/sync`, null, { params }).then(({ data }) => data)
export const generateReport = (payload) => api.post('/reports/generate', payload).then(({ data }) => data)
export const getReports = (params) => api.get('/reports', { params }).then(({ data }) => data)
export const getReport = (reportId) => api.get(`/reports/${reportId}`).then(({ data }) => data)
export const deleteReport = (reportId) => api.delete(`/reports/${reportId}`).then(({ data }) => data)
export const getReportPdfUrl = (reportId) => `${API_BASE_URL}/reports/${reportId}/pdf`

export function getApiError(error) {
  return error?.response?.data?.detail || 'Não foi possível concluir a operação. Tente novamente.'
}
