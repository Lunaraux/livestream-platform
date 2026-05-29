import { get, post } from './http'
import type { PaginatedData, DanmakuResponse, LikeResponse, GiftItem, GiftRankItem, SendGiftResponse } from '@/types'

export const interactionApi = {
  sendDanmaku: (roomId: number, body: { content: string; color?: string; is_pinned?: boolean; pin_duration_seconds?: number }) =>
    post<DanmakuResponse>(`/rooms/${roomId}/danmaku`, body),
  getDanmakuHistory: (roomId: number) =>
    get<DanmakuResponse[]>(`/rooms/${roomId}/danmaku`),
  like: (roomId: number) =>
    post<LikeResponse>(`/rooms/${roomId}/like`),
  getGifts: () =>
    get<GiftItem[]>('/gifts'),
  sendGift: (roomId: number, body: { gift_id: number; quantity: number }) =>
    post<SendGiftResponse>(`/rooms/${roomId}/gifts`, body),
  getGiftRank: (roomId: number) =>
    get<GiftRankItem[]>(`/rooms/${roomId}/gift-rank`),
}
