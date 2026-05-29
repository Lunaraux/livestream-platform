// ── API Response ──
export interface ApiResponse<T = any> {
  code: number
  message: string
  data: T
}

export interface PaginatedData<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

// ── Auth ──
export interface UserInfo {
  id: number
  username: string
  nickname: string
  role: 'audience' | 'streamer' | 'admin'
  avatar_url: string | null
  bio: string | null
  level: number
  follower_count: number
  following_count: number
  streamer_verified: boolean
  created_at: string
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  user_info: UserInfo
}

export interface RegisterRequest {
  username: string
  password: string
  nickname: string
  role: 'audience' | 'streamer'
}

export interface LoginRequest {
  username: string
  password: string
}

// ── Room ──
export interface RoomListItem {
  id: number
  title: string
  description: string
  category: string
  cover_url: string | null
  status: 'idle' | 'live' | 'ended' | 'banned'
  current_viewers: number
  streamer_id: number
  streamer_nickname: string
  streamer_avatar: string | null
  started_at: string | null
}

export interface RoomResponse {
  id: number
  title: string
  description: string
  category: string
  cover_url: string | null
  status: 'idle' | 'live' | 'ended' | 'banned'
  current_viewers: number
  peak_viewers: number
  total_sessions: number
  streamer_id: number
  streamer_nickname: string
  streamer_avatar: string | null
  streamer_bio: string | null
  started_at: string | null
  ended_at: string | null
  created_at: string
  updated_at: string
}

export interface CreateRoomRequest {
  title: string
  description?: string
  category: string
  cover_url?: string
}

export interface RoomStats {
  duration_seconds: number
  peak_viewers: number
  total_likes: number
  total_danmaku: number
  total_gift_fen: number
  total_sessions: number
}

// ── User ──
export interface UserPublicProfile {
  id: number
  username: string
  nickname: string
  role: string
  avatar_url: string | null
  bio: string | null
  level: number
  follower_count: number
  following_count: number
  streamer_verified: boolean
  is_following: boolean | null
  created_at: string
}

export interface FollowerItem {
  id: number
  nickname: string
  avatar_url: string | null
  followed_at: string
}

export interface FollowingItem {
  id: number
  nickname: string
  avatar_url: string | null
  streamer_verified: boolean
  followed_at: string
}

// ── Interaction ──
export interface DanmakuResponse {
  id: number
  user_id: number
  nickname: string
  avatar_url: string | null
  content: string
  color: string
  is_pinned: boolean
  created_at: string
}

export interface LikeResponse {
  room_id: number
  total_likes: number
  user_likes: number
}

export interface GiftItem {
  id: number
  name: string
  icon: string
  price_fen: number
  effect: string
}

export interface GiftRankItem {
  user_id: number
  nickname: string
  avatar_url: string | null
  total_fen: number
}

export interface SendGiftResponse {
  gift_name: string
  quantity: number
  total_fen: number
  balance_after: number
}

// ── Wallet ──
export interface WalletBalance {
  balance_fen: number
  frozen_fen: number
}

export interface RechargeOrder {
  id: number
  order_no: string
  tier: number
  recharge_fen: number
  bonus_fen: number
  total_fen: number
  status: 'pending' | 'paid' | 'failed'
  payment_url: string
  created_at: string
}

export interface TransactionRecord {
  id: number
  type: string
  amount_fen: number
  balance_after: number
  description: string
  created_at: string
}

// ── Settlement ──
export interface EarningsOverview {
  today_fen: number
  month_fen: number
  total_fen: number
  available_fen: number
  pending_fen: number
  frozen_fen: number
}

export interface SettlementBill {
  id: number
  session_id: number
  room_id: number
  room_title: string
  duration_seconds: number
  gift_fen: number
  platform_share_fen: number
  streamer_share_fen: number
  settled_at: string
  created_at: string
}

export interface WithdrawRecord {
  id: number
  amount_fen: number
  status: 'pending' | 'approved' | 'rejected'
  reject_reason: string | null
  created_at: string
  processed_at: string | null
}

// ── Dashboard ──
export interface PlatformRealtime {
  online_users: number
  live_rooms: number
  today_new_users: number
  today_recharge_fen: number
  today_gift_fen: number
  danmaku_per_minute: number
}

export interface TrendData {
  dates: string[]
  new_users: number[]
  revenue_fen: number[]
  live_sessions: number[]
}

export interface RoomRankItem {
  room_id: number
  title: string
  streamer_nickname: string
  current_viewers: number
  category: string
}

export interface StreamerLiveStats {
  online_viewers: number
  cumulative_viewers: number
  danmaku_count: number
  like_count: number
  gift_fen: number
  duration_seconds: number
}

export interface HistorySession {
  session_id: number
  started_at: string
  ended_at: string
  duration_seconds: number
  peak_viewers: number
  gift_fen: number
}

// ── Admin ──
export interface AdminUserItem {
  id: number
  username: string
  nickname: string
  role: string
  avatar_url: string | null
  level: number
  streamer_verified: boolean
  is_banned: boolean
  created_at: string
}

export interface ForbiddenWord {
  id: number
  word: string
  created_at: string
}

// ── WebSocket ──
export interface WsMessage {
  type: string
  data: any
}
