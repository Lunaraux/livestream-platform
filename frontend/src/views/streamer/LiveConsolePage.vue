<template>
  <div class="live-console-page">
    <h2>开播控制台</h2>

    <div v-if="!room" class="empty">
      <el-empty description="你还没有直播间">
        <el-button type="primary" @click="$router.push('/streamer/room')">去创建</el-button>
      </el-empty>
    </div>

    <template v-else>
      <el-row :gutter="16">
        <el-col :span="16">
          <el-card shadow="never" class="live-card">
            <template #header>
              <div class="live-header">
                <span>直播画面</span>
                <el-tag :type="room.status === 'live' ? 'danger' : 'info'">
                  {{ statusLabels[room.status] }}
                </el-tag>
              </div>
            </template>
            <div class="live-preview">
              <img v-if="room.cover_url" :src="room.cover_url" class="preview-img" />
              <div v-else class="preview-placeholder">
                <el-icon :size="64"><VideoCamera /></el-icon>
                <p>{{ room.status === 'live' ? '直播中' : '未开播' }}</p>
              </div>
            </div>
            <div class="live-controls">
              <el-button
                v-if="room.status === 'idle'"
                type="success"
                size="large"
                @click="startStream"
              >
                开始直播
              </el-button>
              <el-button
                v-if="room.status === 'live'"
                type="danger"
                size="large"
                @click="endStream"
              >
                结束直播
              </el-button>
            </div>
          </el-card>
        </el-col>

        <el-col :span="8">
          <!-- Live stats -->
          <el-card shadow="never" class="stats-card">
            <template #header>本场数据</template>
            <div v-if="liveStats">
              <div class="stat-row">
                <span class="label">在线观众</span>
                <span class="value">{{ liveStats.online_viewers }}</span>
              </div>
              <div class="stat-row">
                <span class="label">累计观众</span>
                <span class="value">{{ liveStats.cumulative_viewers }}</span>
              </div>
              <div class="stat-row">
                <span class="label">弹幕数</span>
                <span class="value">{{ liveStats.danmaku_count }}</span>
              </div>
              <div class="stat-row">
                <span class="label">点赞数</span>
                <span class="value">{{ liveStats.like_count }}</span>
              </div>
              <div class="stat-row">
                <span class="label">礼物收入</span>
                <span class="value">¥{{ fenToYuan(liveStats.gift_fen) }}</span>
              </div>
            </div>
            <div v-else class="no-data">暂无数据</div>
          </el-card>

          <!-- Room info -->
          <el-card shadow="never" class="room-info-card">
            <template #header>直播间信息</template>
            <p><strong>标题：</strong>{{ room.title }}</p>
            <p><strong>分类：</strong>{{ categoryLabels[room.category] || room.category }}</p>
            <p><strong>累计直播：</strong>{{ room.total_sessions }} 次</p>
            <p><strong>峰值观众：</strong>{{ room.peak_viewers }}</p>
          </el-card>
        </el-col>
      </el-row>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { roomApi, dashboardApi } from '@/api'
import { categoryLabels, statusLabels, fenToYuan } from '@/utils/format'
import { ElMessage } from 'element-plus'
import { VideoCamera } from '@element-plus/icons-vue'
import type { RoomResponse, StreamerLiveStats } from '@/types'

const room = ref<RoomResponse | null>(null)
const liveStats = ref<StreamerLiveStats | null>(null)

onMounted(async () => {
  try {
    // Find user's room
    const data = await roomApi.list()
    const myRooms = data.items.filter((r) => r.status !== 'ended')
    if (myRooms.length > 0) {
      room.value = await roomApi.detail(myRooms[0].id)
    }
    // Load live stats
    try {
      liveStats.value = await dashboardApi.streamerLive()
    } catch { /* not live */ }
  } catch { /* no room */ }
})

async function startStream() {
  if (!room.value) return
  try {
    room.value = await roomApi.start(room.value.id)
    ElMessage.success('开播成功')
    // Refresh stats
    try { liveStats.value = await dashboardApi.streamerLive() } catch { /* */ }
  } catch { /* handled */ }
}

async function endStream() {
  if (!room.value) return
  try {
    await roomApi.end(room.value.id)
    ElMessage.success('直播已结束')
    room.value = await roomApi.detail(room.value.id)
    liveStats.value = null
  } catch { /* handled */ }
}
</script>

<style scoped>
.live-console-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.live-console-page h2 {
  margin: 0 0 20px;
}

.live-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.live-preview {
  aspect-ratio: 16/9;
  background: #1a1a2e;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  margin-bottom: 16px;
}

.preview-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.preview-placeholder {
  color: #666;
  text-align: center;
}

.preview-placeholder p {
  margin-top: 12px;
}

.live-controls {
  display: flex;
  justify-content: center;
  gap: 12px;
}

.stats-card {
  margin-bottom: 16px;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.stat-row:last-child {
  border-bottom: none;
}

.stat-row .label {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.stat-row .value {
  font-weight: 600;
  color: var(--el-color-primary);
}

.no-data {
  text-align: center;
  color: var(--el-text-color-placeholder);
  padding: 20px;
}

.room-info-card p {
  margin: 8px 0;
  font-size: 14px;
}

.empty {
  padding: 60px 0;
}
</style>
