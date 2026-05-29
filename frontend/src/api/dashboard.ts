import { get, post, del } from './http'
import type {
  PaginatedData, PlatformRealtime, TrendData, RoomRankItem, RoomListItem,
  StreamerLiveStats, HistorySession, AdminUserItem, ForbiddenWord,
  EarningsOverview, SettlementBill, WithdrawRecord,
} from '@/types'

export const dashboardApi = {
  // Admin
  platformRealtime: () => get<PlatformRealtime>('/admin/dashboard/realtime'),
  platformTrend: (period = '7d') => get<TrendData>('/admin/dashboard/trend', { period }),
  roomRank: () => get<RoomRankItem[]>('/admin/dashboard/room-rank'),
  funnel: () => get<any>('/admin/dashboard/funnel'),
  // Streamer
  streamerLive: () => get<StreamerLiveStats>('/streamer/dashboard/live'),
  streamerHistory: () => get<HistorySession[]>('/streamer/dashboard/history'),
}

export const adminApi = {
  // Users
  listUsers: (params?: { page?: number; page_size?: number; role?: string }) =>
    get<PaginatedData<AdminUserItem>>('/admin/users', params),
  banUser: (userId: number, body: { reason: string; duration_hours: number }) =>
    post<any>(`/admin/users/${userId}/ban`, body),
  unbanUser: (userId: number) => post<any>(`/admin/users/${userId}/unban`),
  verifyStreamer: (userId: number, body: { approved: boolean; reject_reason?: string }) =>
    post<any>(`/admin/streamers/${userId}/verify`, body),
  // Rooms
  listAdminRooms: (params?: { page?: number; page_size?: number }) =>
    get<PaginatedData<RoomListItem>>('/admin/rooms', params),
  banRoom: (roomId: number, reason: string) =>
    post<any>(`/admin/rooms/${roomId}/ban`, { reason }),
  unbanRoom: (roomId: number) => post<any>(`/admin/rooms/${roomId}/unban`),
  // Withdraw
  listWithdraws: (params?: { page?: number; page_size?: number }) =>
    get<PaginatedData<WithdrawRecord>>('/admin/withdraw', params),
  approveWithdraw: (id: number) => post<WithdrawRecord>(`/admin/withdraw/${id}/approve`),
  rejectWithdraw: (id: number, reason: string) =>
    post<WithdrawRecord>(`/admin/withdraw/${id}/reject`, { reject_reason: reason }),
  revenue: (params?: { start_date?: string; end_date?: string }) =>
    get<SettlementBill[]>('/admin/platform/revenue', params),
  // Forbidden words
  listForbiddenWords: () => get<ForbiddenWord[]>('/admin/forbidden-words'),
  addForbiddenWord: (word: string) => post<ForbiddenWord>('/admin/forbidden-words', { word }),
  deleteForbiddenWord: (id: number) => del<any>(`/admin/forbidden-words/${id}`),
}
