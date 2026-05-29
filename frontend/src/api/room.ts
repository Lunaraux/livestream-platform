import { get, post, put, del } from './http'
import type {
  PaginatedData, RoomListItem, RoomResponse, RoomStats,
  CreateRoomRequest, UserPublicProfile,
  FollowerItem, FollowingItem,
} from '@/types'

export const roomApi = {
  list: (params?: { page?: number; page_size?: number; category?: string; sort_by?: string }) =>
    get<PaginatedData<RoomListItem>>('/rooms', params),
  recommended: () => get<RoomListItem[]>('/rooms/recommended'),
  search: (q: string, page = 1, pageSize = 20) =>
    get<PaginatedData<RoomListItem>>('/rooms/search', { q, page, page_size: pageSize }),
  detail: (id: number) => get<RoomResponse>(`/rooms/${id}`),
  create: (body: CreateRoomRequest) => post<RoomResponse>('/rooms', body),
  start: (id: number) => post<RoomResponse>(`/rooms/${id}/start`),
  end: (id: number) => post<RoomStats>(`/rooms/${id}/end`),
  update: (id: number, body: Partial<CreateRoomRequest>) => put<RoomResponse>(`/rooms/${id}`, body),
}

export const userApi = {
  profile: (id: number) => get<UserPublicProfile>(`/users/${id}`),
  updateProfile: (body: UpdateProfileRequest) => put<{ id: number; nickname: string; avatar_url: string | null; bio: string | null }>('/users/me', body),
  changePassword: (body: { old_password: string; new_password: string }) => post<null>('/users/me/password', body),
  follow: (id: number) => post<{ message: string }>(`/users/${id}/follow`),
  unfollow: (id: number) => del<{ message: string }>(`/users/${id}/follow`),
  getFollowing: (page = 1, pageSize = 20) =>
    get<PaginatedData<FollowingItem>>('/users/me/following', { page, page_size: pageSize }),
  getFollowers: (page = 1, pageSize = 20) =>
    get<PaginatedData<FollowerItem>>('/users/me/followers', { page, page_size: pageSize }),
  applyStreamer: (body: { real_name: string; id_number: string }) =>
    post<{ message: string }>('/users/me/apply-streamer', body),
}

export interface UpdateProfileRequest {
  nickname?: string
  avatar_url?: string
  bio?: string
}
