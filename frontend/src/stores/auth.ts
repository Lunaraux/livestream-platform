import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api'
import type { UserInfo, LoginResponse, LoginRequest, RegisterRequest } from '@/types'
import router from '@/router'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserInfo | null>(null)
  const accessToken = ref<string | null>(null)
  const refreshToken = ref<string | null>(null)

  const isLoggedIn = computed(() => !!accessToken.value && !!user.value)
  const isAdmin = computed(() => user.value?.role === 'admin')
  const isStreamer = computed(() => user.value?.role === 'streamer')
  const isVerifiedStreamer = computed(() => isStreamer.value && user.value?.streamer_verified)

  // Initialize from localStorage
  function initFromStorage() {
    const storedUser = localStorage.getItem('user')
    const storedAccess = localStorage.getItem('access_token')
    const storedRefresh = localStorage.getItem('refresh_token')
    if (storedUser && storedAccess) {
      try {
        user.value = JSON.parse(storedUser)
        accessToken.value = storedAccess
        refreshToken.value = storedRefresh
      } catch {
        clearAuth()
      }
    }
  }

  function setAuth(data: LoginResponse) {
    user.value = data.user_info
    accessToken.value = data.access_token
    refreshToken.value = data.refresh_token
    localStorage.setItem('user', JSON.stringify(data.user_info))
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)
  }

  function clearAuth() {
    user.value = null
    accessToken.value = null
    refreshToken.value = null
    localStorage.removeItem('user')
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  }

  async function login(body: LoginRequest) {
    const data = await authApi.login(body)
    setAuth(data)
  }

  async function register(body: RegisterRequest) {
    await authApi.register(body)
  }

  async function logout() {
    try {
      if (refreshToken.value) {
        await authApi.logout(refreshToken.value)
      }
    } catch {
      // Ignore
    }
    clearAuth()
    router.push('/login')
  }

  async function fetchMe() {
    try {
      const data = await authApi.me()
      user.value = data
      localStorage.setItem('user', JSON.stringify(data))
    } catch {
      // Token invalid
      clearAuth()
    }
  }

  return {
    user,
    accessToken,
    refreshToken,
    isLoggedIn,
    isAdmin,
    isStreamer,
    isVerifiedStreamer,
    initFromStorage,
    login,
    register,
    logout,
    fetchMe,
    clearAuth,
  }
})
