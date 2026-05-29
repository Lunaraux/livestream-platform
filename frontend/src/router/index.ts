import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    // ── Public ──
    {
      path: '/',
      name: 'Home',
      component: () => import('@/views/public/HomePage.vue'),
    },
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/public/LoginPage.vue'),
      meta: { guest: true },
    },
    {
      path: '/register',
      name: 'Register',
      component: () => import('@/views/public/RegisterPage.vue'),
      meta: { guest: true },
    },
    {
      path: '/rooms/:id',
      name: 'Room',
      component: () => import('@/views/public/RoomPage.vue'),
    },
    // ── User ──
    {
      path: '/wallet',
      name: 'Wallet',
      component: () => import('@/views/user/WalletPage.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/following',
      name: 'Following',
      component: () => import('@/views/user/FollowingPage.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/profile',
      name: 'Profile',
      component: () => import('@/views/user/ProfilePage.vue'),
      meta: { requiresAuth: true },
    },
    // ── Streamer ──
    {
      path: '/streamer/room',
      name: 'StreamerRoom',
      component: () => import('@/views/streamer/RoomManagePage.vue'),
      meta: { requiresAuth: true, requiresStreamer: true },
    },
    {
      path: '/streamer/live',
      name: 'StreamerLive',
      component: () => import('@/views/streamer/LiveConsolePage.vue'),
      meta: { requiresAuth: true, requiresStreamer: true },
    },
    {
      path: '/streamer/earnings',
      name: 'StreamerEarnings',
      component: () => import('@/views/streamer/EarningsPage.vue'),
      meta: { requiresAuth: true, requiresStreamer: true },
    },
    {
      path: '/streamer/dashboard',
      name: 'StreamerDashboard',
      component: () => import('@/views/streamer/DashboardPage.vue'),
      meta: { requiresAuth: true, requiresStreamer: true },
    },
    // ── Admin ──
    {
      path: '/admin/dashboard',
      name: 'AdminDashboard',
      component: () => import('@/views/admin/AdminDashboardPage.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/admin/users',
      name: 'AdminUsers',
      component: () => import('@/views/admin/AdminUsersPage.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/admin/rooms',
      name: 'AdminRooms',
      component: () => import('@/views/admin/AdminRoomsPage.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/admin/withdraw',
      name: 'AdminWithdraw',
      component: () => import('@/views/admin/AdminWithdrawPage.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/admin/gifts',
      name: 'AdminGifts',
      component: () => import('@/views/admin/AdminGiftsPage.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
  ],
})

// Navigation guards
router.beforeEach(async (to, _from, next) => {
  const auth = useAuthStore()

  // Initialize from storage on first navigation
  if (!auth.isLoggedIn) {
    auth.initFromStorage()
  }

  // Guest-only pages (login/register) — redirect to home if logged in
  if (to.meta.guest && auth.isLoggedIn) {
    return next('/')
  }

  // Auth-required pages
  if (to.meta.requiresAuth && !auth.isLoggedIn) {
    return next('/login')
  }

  // Streamer-required pages
  if (to.meta.requiresStreamer) {
    if (auth.isLoggedIn && auth.user?.role === 'audience') {
      return next('/')
    }
    if (auth.isLoggedIn && !auth.isStreamer && !auth.isAdmin) {
      return next('/')
    }
    // Refresh user info to get latest verification status
    if (auth.isLoggedIn && auth.user) {
      await auth.fetchMe()
    }
  }

  // Admin-required pages
  if (to.meta.requiresAdmin && !auth.isAdmin) {
    return next('/')
  }

  next()
})

export default router
