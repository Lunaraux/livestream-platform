import { get, post } from './http'
import type { LoginResponse, RegisterRequest, LoginRequest, UserInfo } from '@/types'

export const authApi = {
  login: (body: LoginRequest) => post<LoginResponse>('/auth/login', body),
  register: (body: RegisterRequest) => post<UserInfo>('/auth/register', body),
  refresh: (refreshToken: string) => post<{ access_token: string }>('/auth/refresh', { refresh_token: refreshToken }),
  logout: (refreshToken: string) => post<null>('/auth/logout', { refresh_token: refreshToken }),
  me: () => get<UserInfo>('/auth/me'),
}
