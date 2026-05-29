<template>
  <div class="dashboard-page">
    <h2>数据大屏</h2>

    <!-- Live stats -->
    <el-row :gutter="16" class="row">
      <el-col :span="6" v-for="stat in liveStats" :key="stat.label">
        <el-card shadow="never">
          <div class="stat-card">
            <span class="stat-label">{{ stat.label }}</span>
            <span class="stat-value">{{ stat.value }}</span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- History chart placeholder -->
    <el-card shadow="never">
      <template #header>最近直播记录</template>
      <el-table :data="history" stripe style="width:100%">
        <el-table-column label="开播时间" width="170">
          <template #default="{ row }">{{ formatTime(row.started_at) }}</template>
        </el-table-column>
        <el-table-column label="下播时间" width="170">
          <template #default="{ row }">{{ formatTime(row.ended_at) }}</template>
        </el-table-column>
        <el-table-column label="时长" width="120">
          <template #default="{ row }">{{ formatDuration(row.duration_seconds) }}</template>
        </el-table-column>
        <el-table-column label="峰值观众" width="100">
          <template #default="{ row }">{{ row.peak_viewers }}</template>
        </el-table-column>
        <el-table-column label="礼物收入" width="120">
          <template #default="{ row }">¥{{ fenToYuan(row.gift_fen) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { dashboardApi } from '@/api'
import { fenToYuan, formatTime, formatDuration } from '@/utils/format'
import type { StreamerLiveStats, HistorySession } from '@/types'

const liveData = ref<StreamerLiveStats | null>(null)
const history = ref<HistorySession[]>([])

const liveStats = computed(() => {
  if (!liveData.value) return []
  return [
    { label: '在线观众', value: liveData.value.online_viewers },
    { label: '累计观众', value: liveData.value.cumulative_viewers },
    { label: '弹幕数', value: liveData.value.danmaku_count },
    { label: '礼物收入', value: `¥${fenToYuan(liveData.value.gift_fen)}` },
  ]
})

onMounted(async () => {
  try {
    liveData.value = await dashboardApi.streamerLive()
  } catch { /* not live */ }
  try {
    history.value = await dashboardApi.streamerHistory()
  } catch { /* */ }
})
</script>

<style scoped>
.dashboard-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.dashboard-page h2 {
  margin: 0 0 20px;
}

.row {
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
  font-size: 24px;
  font-weight: 700;
  color: var(--el-color-primary);
}
</style>
