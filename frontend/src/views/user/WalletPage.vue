<template>
  <div class="wallet-page">
    <h2>我的钱包</h2>

    <!-- Balance card -->
    <el-row :gutter="16" class="balance-row">
      <el-col :span="8">
        <el-card shadow="never">
          <div class="stat-item">
            <span class="stat-label">可用余额</span>
            <span class="stat-value">¥{{ fenToYuan(balance.balance_fen) }}</span>
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never">
          <div class="stat-item">
            <span class="stat-label">冻结余额</span>
            <span class="stat-value">¥{{ fenToYuan(balance.frozen_fen) }}</span>
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never">
          <div class="stat-item">
            <span class="stat-label">总余额</span>
            <span class="stat-value" style="color:var(--el-color-primary)">
              ¥{{ fenToYuan(balance.balance_fen + balance.frozen_fen) }}
            </span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Recharge -->
    <el-card shadow="never" class="section-card">
      <template #header>充值</template>
      <div class="recharge-grid">
        <div
          v-for="tier in rechargeTiers"
          :key="tier.tier"
          class="recharge-item"
          @click="doRecharge(tier.tier)"
        >
          <span class="emoji">{{ tier.emoji }}</span>
          <span class="amount">¥{{ (tier.recharge_fen / 100).toFixed(0) }}</span>
          <span v-if="tier.bonus_fen" class="bonus">送{{ fenToYuan(tier.bonus_fen) }}元</span>
        </div>
      </div>
    </el-card>

    <!-- Tabs: transactions / recharge history -->
    <el-card shadow="never" class="section-card">
      <template #header>交易记录</template>
      <el-table :data="transactions" stripe style="width:100%">
        <el-table-column prop="description" label="说明" min-width="200" />
        <el-table-column label="金额" width="120">
          <template #default="{ row }">
            <span :style="{ color: row.amount_fen > 0 ? '#67C23A' : '#F56C6C' }">
              {{ row.amount_fen > 0 ? '+' : '' }}{{ fenToYuan(row.amount_fen) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
      </el-table>
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="txPage"
          :page-size="txPageSize"
          :total="txTotal"
          layout="prev, pager, next"
          @current-change="fetchTransactions"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { walletApi } from '@/api'
import { fenToYuan, formatTime } from '@/utils/format'
import { ElMessage } from 'element-plus'
import type { WalletBalance, TransactionRecord } from '@/types'

const balance = ref<WalletBalance>({ balance_fen: 0, frozen_fen: 0 })
const transactions = ref<TransactionRecord[]>([])
const txPage = ref(1)
const txPageSize = 20
const txTotal = ref(0)

const rechargeTiers = [
  { tier: 1, recharge_fen: 1000, bonus_fen: 0, emoji: '💎' },
  { tier: 2, recharge_fen: 5000, bonus_fen: 500, emoji: '💎💎' },
  { tier: 3, recharge_fen: 10000, bonus_fen: 1500, emoji: '💎💎💎' },
  { tier: 4, recharge_fen: 50000, bonus_fen: 10000, emoji: '👑' },
  { tier: 5, recharge_fen: 100000, bonus_fen: 25000, emoji: '👑👑' },
  { tier: 6, recharge_fen: 500000, bonus_fen: 150000, emoji: '👑👑👑' },
]

onMounted(() => {
  fetchBalance()
  fetchTransactions()
})

async function fetchBalance() {
  try {
    balance.value = await walletApi.balance()
  } catch { /* ignore */ }
}

async function fetchTransactions() {
  try {
    const data = await walletApi.transactions(txPage.value, txPageSize)
    transactions.value = data.items
    txTotal.value = data.total
  } catch { /* ignore */ }
}

async function doRecharge(tier: number) {
  try {
    const order = await walletApi.recharge(tier)
    // Simulate payment
    await walletApi.payRecharge(order.id)
    ElMessage.success('充值成功')
    fetchBalance()
    fetchTransactions()
  } catch { /* handled */ }
}
</script>

<style scoped>
.wallet-page {
  max-width: 1000px;
  margin: 0 auto;
  padding: 24px;
}

.wallet-page h2 {
  margin: 0 0 20px;
}

.balance-row {
  margin-bottom: 20px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.stat-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
}

.section-card {
  margin-bottom: 20px;
}

.recharge-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
}

.recharge-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.recharge-item:hover {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.recharge-item .emoji {
  font-size: 28px;
}

.recharge-item .amount {
  font-size: 18px;
  font-weight: 600;
  margin-top: 8px;
}

.recharge-item .bonus {
  font-size: 12px;
  color: var(--el-color-warning);
  margin-top: 4px;
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
</style>
