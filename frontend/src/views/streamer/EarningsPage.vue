<template>
  <div class="earnings-page">
    <h2>收益中心</h2>

    <!-- Overview cards -->
    <el-row :gutter="16" class="overview-row">
      <el-col :span="6" v-for="stat in stats" :key="stat.label">
        <el-card shadow="never">
          <div class="stat-card">
            <span class="stat-label">{{ stat.label }}</span>
            <span class="stat-value">¥{{ fenToYuan(stat.value) }}</span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Withdraw -->
    <el-card shadow="never" class="section-card">
      <template #header>申请提现</template>
      <div class="withdraw-form">
        <span>可提现余额：<strong>¥{{ fenToYuan(overview?.available_fen || 0) }}</strong></span>
        <el-input-number
          v-model="withdrawAmount"
          :min="100"
          :max="(overview?.available_fen || 0) / 100"
          :step="100"
          style="width:200px;margin:0 12px"
        />
        <span>元</span>
        <el-button
          type="warning"
          :loading="withdrawing"
          :disabled="!withdrawAmount || withdrawAmount < 100"
          @click="doWithdraw"
        >
          申请提现
        </el-button>
        <span class="min-note">最低提现 100 元</span>
      </div>
    </el-card>

    <!-- Earnings detail -->
    <el-card shadow="never" class="section-card">
      <template #header>收益明细</template>
      <el-table :data="bills" stripe style="width:100%">
        <el-table-column prop="room_title" label="直播间" min-width="150" />
        <el-table-column label="直播时长" width="120">
          <template #default="{ row }">{{ formatDuration(row.duration_seconds) }}</template>
        </el-table-column>
        <el-table-column label="礼物收入" width="120">
          <template #default="{ row }">¥{{ fenToYuan(row.gift_fen) }}</template>
        </el-table-column>
        <el-table-column label="平台分成" width="120">
          <template #default="{ row }">¥{{ fenToYuan(row.platform_share_fen) }}</template>
        </el-table-column>
        <el-table-column label="主播收益" width="120">
          <template #default="{ row }">¥{{ fenToYuan(row.streamer_share_fen) }}</template>
        </el-table-column>
        <el-table-column label="结算时间" width="180">
          <template #default="{ row }">{{ formatTime(row.settled_at) }}</template>
        </el-table-column>
      </el-table>
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="prev, pager, next"
          @current-change="fetchBills"
        />
      </div>
    </el-card>

    <!-- Withdraw history -->
    <el-card shadow="never" class="section-card">
      <template #header>提现记录</template>
      <el-table :data="withdraws" stripe style="width:100%">
        <el-table-column label="金额" width="120">
          <template #default="{ row }">¥{{ fenToYuan(row.amount_fen) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="withdrawStatusType(row.status)">
              {{ withdrawStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="reject_reason" label="拒绝原因" min-width="150" />
        <el-table-column label="申请时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="处理时间" width="180">
          <template #default="{ row }">{{ formatTime(row.processed_at) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { settlementApi } from '@/api'
import { fenToYuan, formatTime, formatDuration } from '@/utils/format'
import { ElMessage } from 'element-plus'
import type { EarningsOverview, SettlementBill, WithdrawRecord } from '@/types'

const overview = ref<EarningsOverview | null>(null)
const bills = ref<SettlementBill[]>([])
const withdraws = ref<WithdrawRecord[]>([])
const page = ref(1)
const pageSize = 20
const total = ref(0)
const withdrawAmount = ref(0)
const withdrawing = ref(false)

const stats = computed(() => [
  { label: '今日收益', value: overview.value?.today_fen || 0 },
  { label: '本月收益', value: overview.value?.month_fen || 0 },
  { label: '累计收益', value: overview.value?.total_fen || 0 },
  { label: '待结算', value: overview.value?.pending_fen || 0 },
])

onMounted(() => {
  fetchOverview()
  fetchBills()
  fetchWithdraws()
})

async function fetchOverview() {
  try { overview.value = await settlementApi.earningsOverview() } catch { /* */ }
}

async function fetchBills() {
  try {
    const data = await settlementApi.earningsDetail({ page: page.value, page_size: pageSize })
    bills.value = data.items
    total.value = data.total
  } catch { /* */ }
}

async function fetchWithdraws() {
  try {
    const data = await settlementApi.withdrawHistory(1, 100)
    withdraws.value = data.items
  } catch { /* */ }
}

async function doWithdraw() {
  if (!withdrawAmount.value || withdrawAmount.value < 100) return
  withdrawing.value = true
  try {
    await settlementApi.withdraw(withdrawAmount.value * 100)
    ElMessage.success('提现申请已提交')
    withdrawAmount.value = 0
    fetchOverview()
    fetchWithdraws()
  } catch { /* handled */ }
  finally { withdrawing.value = false }
}

function withdrawStatusType(status: string) {
  return status === 'approved' ? 'success' : status === 'rejected' ? 'danger' : 'warning'
}

function withdrawStatusLabel(status: string) {
  return status === 'approved' ? '已通过' : status === 'rejected' ? '已拒绝' : '处理中'
}
</script>

<style scoped>
.earnings-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px;
}

.earnings-page h2 {
  margin: 0 0 20px;
}

.overview-row {
  margin-bottom: 20px;
}

.stat-card {
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
  font-size: 22px;
  font-weight: 700;
  color: var(--el-color-warning);
}

.section-card {
  margin-bottom: 20px;
}

.withdraw-form {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.min-note {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  margin-left: 12px;
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
</style>
