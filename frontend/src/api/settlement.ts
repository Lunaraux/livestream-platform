import { get, post } from './http'
import type { PaginatedData, EarningsOverview, SettlementBill, WithdrawRecord } from '@/types'

export const settlementApi = {
  earningsOverview: () => get<EarningsOverview>('/streamer/earnings'),
  earningsDetail: (params?: { page?: number; page_size?: number; start_date?: string; end_date?: string }) =>
    get<PaginatedData<SettlementBill>>('/streamer/earnings/detail', params),
  withdraw: (amountFen: number) => post<WithdrawRecord>('/streamer/withdraw', { amount_fen: amountFen }),
  withdrawHistory: (page = 1, pageSize = 20) =>
    get<PaginatedData<WithdrawRecord>>('/streamer/withdraw-history', { page, page_size: pageSize }),
}
