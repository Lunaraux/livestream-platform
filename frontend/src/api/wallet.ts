import { get, post } from './http'
import type { PaginatedData, WalletBalance, RechargeOrder, TransactionRecord } from '@/types'

export const walletApi = {
  balance: () => get<WalletBalance>('/wallet/balance'),
  recharge: (tier: number) => post<RechargeOrder>('/wallet/recharge', { tier }),
  payRecharge: (orderId: number) => post<{ message: string }>(`/wallet/recharge/${orderId}/pay`),
  rechargeHistory: (page = 1, pageSize = 20) =>
    get<PaginatedData<RechargeOrder>>('/wallet/recharge-history', { page, page_size: pageSize }),
  transactions: (page = 1, pageSize = 20, type?: string) =>
    get<PaginatedData<TransactionRecord>>('/wallet/transactions', { page, page_size: pageSize, type }),
}
