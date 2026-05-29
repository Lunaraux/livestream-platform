<template>
  <div class="admin-dashboard-page">
    <h2>平台数据大屏</h2>

    <!-- Realtime overview -->
    <el-row :gutter="16" class="row">
      <el-col :span="6" v-for="stat in realtimeStats" :key="stat.label">
        <el-card shadow="never">
          <div class="stat-card">
            <span class="stat-label">{{ stat.label }}</span>
            <span class="stat-value">{{ stat.value }}</span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Trend -->
    <el-card shadow="never" class="card">
      <template #header>
        <div class="card-header">
          <span>平台趋势</span>
          <el-radio-group v-model="trendPeriod" size="small" @change="fetchTrend">
            <el-radio-button value="7d">近7天</el-radio-button>
            <el-radio-button value="30d">近30天</el-radio-button>
            <el-radio-button value="90d">近90天</el-radio-button>
          </el-radio-group>
        </div>
      </template>
      <div v-if="trendData" class="chart-placeholder">
        <p>趋势数据已加载：{{ trendData.dates?.length || 0 }} 个数据点</p>
        <el-table :data="trendTable" style="width:100%" max-height="300">
          <el-table-column prop="date" label="日期" width="120" />
          <el-table-column prop="newUsers" label="新增用户" />
          <el-table-column prop="revenue" label="营收(元)" />
          <el-table-column prop="sessions" label="直播场次" />
        </el-table>
      </div>
    </el-card>

    <!-- Room rank -->
    <el-row :gutter="16">
      <el-col :span="12">
        <el-card shadow="never" class="card">
          <template #header>TOP10 直播间</template>
          <el-table :data="roomRank" stripe style="width:100%">
            <el-table-column type="index" label="#" width="50" />
            <el-table-column prop="title" label="标题" min-width="150" />
            <el-table-column prop="streamer_nickname" label="主播" width="100" />
            <el-table-column prop="current_viewers" label="观众" width="80" />
            <el-table-column label="分类" width="80">
              <template #default="{ row }">
                <el-tag size="small">{{ categoryLabels[row.category] || row.category }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="never" class="card">
          <template #header>用户漏斗</template>
          <div v-if="funnelData" class="funnel">
            <div class="funnel-step">
              <span class="f-label">注册用户</span>
              <span class="f-value">{{ funnelData.registered }}</span>
            </div>
            <div class="funnel-step">
              <span class="f-label">充值用户</span>
              <span class="f-value">{{ funnelData.consuming }}</span>
            </div>
            <div class="funnel-step">
              <span class="f-label">活跃主播</span>
              <span class="f-value">{{ funnelData.active_streamers }}</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { dashboardApi } from '@/api'
import { categoryLabels, fenToYuan } from '@/utils/format'
import type { PlatformRealtime, TrendData, RoomRankItem } from '@/types'

const realtime = ref<PlatformRealtime | null>(null)
const trendData = ref<TrendData | null>(null)
const trendPeriod = ref('7d')
const roomRank = ref<RoomRankItem[]>([])
const funnelData = ref<any>(null)

const realtimeStats = computed(() => {
  if (!realtime.value) return []
  return [
    { label: '在线用户', value: realtime.value.online_users },
    { label: '直播中', value: realtime.value.live_rooms },
    { label: '今日新增', value: realtime.value.today_new_users },
    { label: '今日收入', value: `¥${fenToYuan(realtime.value.today_gift_fen)}` },
  ]
})

const trendTable = computed(() => {
  if (!trendData.value) return []
  return (trendData.value.dates || []).map((date: string, i: number) => ({
    date,
    newUsers: trendData.value!.new_users[i] || 0,
    revenue: fenToYuan(trendData.value!.revenue_fen[i] || 0),
    sessions: trendData.value!.live_sessions[i] || 0,
  }))
})

onMounted(() => {
  fetchRealtime()
  fetchTrend()
  fetchRoomRank()
  fetchFunnel()
})

async function fetchRealtime() {
  try { realtime.value = await dashboardApi.platformRealtime() } catch { /* */ }
}

async function fetchTrend() {
  try { trendData.value = await dashboardApi.platformTrend(trendPeriod.value) } catch { /* */ }
}

async function fetchRoomRank() {
  try { roomRank.value = await dashboardApi.roomRank() } catch { /* */ }
}

async function fetchFunnel() {
  try { funnelData.value = await dashboardApi.funnel() } catch { /* */ }
}
</script>

<style scoped>
.admin-dashboard-page {
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px;
}

.admin-dashboard-page h2 {
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
  font-size: 22px;
  font-weight: 700;
  color: var(--el-color-primary);
}

.card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chart-placeholder {
  min-height: 200px;
}

.chart-placeholder p {
  color: var(--el-text-color-secondary);
  margin-bottom: 12px;
}

.funnel {
  display: flex;
  justify-content: space-around;
  padding: 20px 0;
}

.funnel-step {
  text-align: center;
  padding: 20px 40px;
  border: 2px solid var(--el-color-primary-light-5);
  border-radius: 8px;
}

.f-label {
  display: block;
  font-size: 14px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}

.f-value {
  display: block;
  font-size: 28px;
  font-weight: 700;
  color: var(--el-color-primary);
}
</style>
