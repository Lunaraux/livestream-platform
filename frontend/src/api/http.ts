import axios from 'axios'
import type { ApiResponse } from '@/types'
import { ElMessage } from 'element-plus'

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api',
  timeout: 15000,
})

// Request interceptor — attach token
http.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor — unwrap + error handling
http.interceptors.response.use(
  (response) => {
    const body: ApiResponse = response.data
    if (body.code !== 0) {
      ElMessage.error(body.message || '请求失败')
      return Promise.reject(new Error(body.message || '请求失败'))
    }
    return response
  },
  async (error) => {
    if (error.response?.status === 401) {
      const refreshed = await tryRefreshToken()
      if (refreshed) {
        // Retry original request
        return http(error.config)
      }
      // Refresh failed — force logout
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      localStorage.removeItem('user')
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    const msg = error.response?.data?.message || error.message || '网络错误'
    ElMessage.error(msg)
    return Promise.reject(error)
  },
)

async function tryRefreshToken(): Promise<boolean> {
  const refreshToken = localStorage.getItem('refresh_token')
  if (!refreshToken) return false
  try {
    const { data } = await axios.post('/api/auth/refresh', {
      refresh_token: refreshToken,
    })
    if (data.code === 0 && data.data.access_token) {
      localStorage.setItem('access_token', data.data.access_token)
      return true
    }
  } catch {
    // Ignore
  }
  return false
}

// ── Typed request helpers ──

export async function get<T>(url: string, params?: any): Promise<T> {
  const { data } = await http.get<ApiResponse<T>>(url, { params })
  return data.data
}

export async function post<T>(url: string, body?: any): Promise<T> {
  const { data } = await http.post<ApiResponse<T>>(url, body)
  return data.data
}

export async function put<T>(url: string, body?: any): Promise<T> {
  const { data } = await http.put<ApiResponse<T>>(url, body)
  return data.data
}

export async function del<T>(url: string): Promise<T> {
  const { data } = await http.delete<ApiResponse<T>>(url)
  return data.data
}

export default http
