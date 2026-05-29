<template>
  <div class="room-page">
    <div v-if="!room" class="loading-wrap">
      <el-skeleton animated />
    </div>

    <template v-else>
      <!-- Room content: main area + sidebar -->
      <div class="room-layout">
        <!-- Left: player area -->
        <div class="player-area">
          <div class="player">
            <img
              v-if="room.cover_url"
              :src="room.cover_url"
              :alt="room.title"
              class="player-cover"
            />
            <div v-else class="player-placeholder">
              <el-icon :size="64"><VideoCamera /></el-icon>
              <p>{{ room.status === 'live' ? '直播中' : '未开播' }}</p>
            </div>
          </div>

          <!-- Room title & info -->
          <div class="room-meta">
            <h2>{{ room.title }}</h2>
            <div class="room-meta-row">
              <span class="streamer-info">
                <el-avatar :size="32" :src="room.streamer_avatar" />
                <span class="streamer-name">{{ room.streamer_nickname }}</span>
                <el-tag v-if="room.status === 'live'" type="danger" size="small">直播中</el-tag>
                <el-tag v-else type="info" size="small">{{ statusLabels[room.status] }}</el-tag>
              </span>
              <span>{{ room.current_viewers }} 人在看</span>
            </div>
          </div>

          <!-- Gift bar + Like -->
          <div class="action-bar">
            <div class="gift-bar">
              <div
                v-for="gift in gifts"
                :key="gift.id"
                class="gift-item"
                :class="{ selected: selectedGift === gift.id }"
                @click="selectGift(gift)"
              >
                <span class="gift-icon">{{ gift.icon }}</span>
                <span class="gift-name">{{ gift.name }}</span>
                <span class="gift-price">{{ fenToYuan(gift.price_fen) }}元</span>
              </div>
            </div>

            <div class="action-buttons">
              <el-button
                v-if="selectedGift && auth.isLoggedIn"
                type="warning"
                @click="handleSendGift"
              >
                赠送 x{{ giftQuantity }}
              </el-button>
              <el-input-number
                v-if="selectedGift"
                v-model="giftQuantity"
                :min="1"
                :max="99"
                size="small"
                style="width:80px"
              />
              <el-button
                v-if="auth.isLoggedIn"
                type="danger"
                :icon="StarFilled"
                @click="handleLike"
              >
                点赞 {{ likeCount }}
              </el-button>
            </div>
          </div>
        </div>

        <!-- Right: danmaku area -->
        <div class="danmaku-area">
          <!-- Streamer info card -->
          <el-card shadow="never" class="streamer-card">
            <div class="streamer-profile">
              <el-avatar :size="48" :src="room.streamer_avatar" />
              <div class="streamer-detail">
                <p class="s-name">{{ room.streamer_nickname }}</p>
                <p class="s-desc">{{ room.description || '这个人很懒，什么都没写' }}</p>
              </div>
            </div>
            <div class="streamer-stats">
              <span>粉丝 {{ streamerProfile?.follower_count || 0 }}</span>
              <span>等级 {{ streamerProfile?.level || 1 }}</span>
            </div>
            <el-button
              v-if="auth.isLoggedIn && auth.user?.id !== room.streamer_id"
              :type="isFollowing ? 'default' : 'primary'"
              size="small"
              style="width:100%;margin-top:12px"
              @click="toggleFollow"
            >
              {{ isFollowing ? '已关注' : '关注' }}
            </el-button>
          </el-card>

          <!-- Viewer count -->
          <el-card shadow="never" class="viewer-card">
            <span>在线人数：{{ viewerCount }}</span>
          </el-card>

          <!-- Danmaku list -->
          <el-card shadow="never" class="danmaku-list-card">
            <template #header>
              <span>弹幕</span>
            </template>
            <div ref="danmakuListRef" class="danmaku-list">
              <div
                v-for="dm in danmakuList"
                :key="dm.id"
                class="danmaku-item"
              >
                <span class="dm-nickname" :style="{ color: dm.color || '#333' }">
                  {{ dm.nickname }}：
                </span>
                <span class="dm-content">{{ dm.content }}</span>
              </div>
              <div v-if="danmakuList.length === 0" class="dm-empty">
                暂无弹幕
              </div>
            </div>
          </el-card>

          <!-- Danmaku input -->
          <div v-if="auth.isLoggedIn" class="danmaku-input">
            <el-input
              v-model="danmakuText"
              placeholder="发送弹幕..."
              maxlength="100"
              show-word-limit
              @keyup.enter="sendDanmaku"
            >
              <template #append>
                <el-button @click="sendDanmaku" :disabled="!danmakuText.trim()">
                  发送
                </el-button>
              </template>
            </el-input>
          </div>
          <div v-else class="guest-tip">
            <router-link to="/login">登录</router-link>后可发送弹幕和礼物
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { roomApi, interactionApi, userApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { useRoomWebSocket } from '@/composables/useWebSocket'
import { fenToYuan, statusLabels } from '@/utils/format'
import { ElMessage } from 'element-plus'
import { StarFilled, VideoCamera } from '@element-plus/icons-vue'
import type { RoomResponse, DanmakuResponse, GiftItem, UserPublicProfile } from '@/types'

const route = useRoute()
const auth = useAuthStore()

const roomId = ref(Number(route.params.id))
const room = ref<RoomResponse | null>(null)
const gifts = ref<GiftItem[]>([])
const danmakuList = ref<DanmakuResponse[]>([])
const danmakuText = ref('')
const danmakuListRef = ref<HTMLElement>()
const viewerCount = ref(0)
const likeCount = ref(0)
const selectedGift = ref<number | null>(null)
const giftQuantity = ref(1)
const isFollowing = ref(false)
const streamerProfile = ref<UserPublicProfile | null>(null)

const ws = useRoomWebSocket(roomId.value)

// Init
onMounted(async () => {
  try {
    room.value = await roomApi.detail(roomId.value)
    viewerCount.value = room.value.current_viewers
    // Load gifts
    const giftData = await interactionApi.getGifts()
    gifts.value = giftData
    // Load danmaku history
    const history = await interactionApi.getDanmakuHistory(roomId.value)
    danmakuList.value = history
    // Load streamer profile
    try {
      streamerProfile.value = await userApi.profile(room.value!.streamer_id)
      isFollowing.value = streamerProfile.value.is_following ?? false
    } catch { /* ignore */ }
  } catch {
    ElMessage.error('直播间不存在')
  }
})

// WS handlers
watch(() => ws.connected, (val) => {
  if (val) {
    ws.onDanmaku(handleWsDanmaku)
    ws.onLike(handleWsLike)
    ws.onViewerUpdate(handleWsViewer)
  }
}, { immediate: true })

function handleWsDanmaku(data: any) {
  danmakuList.value.push(data as DanmakuResponse)
  // Keep max 200 items
  if (danmakuList.value.length > 200) {
    danmakuList.value = danmakuList.value.slice(-200)
  }
  nextTick(() => {
    if (danmakuListRef.value) {
      danmakuListRef.value.scrollTop = danmakuListRef.value.scrollHeight
    }
  })
}

function handleWsLike(data: any) {
  likeCount.value = data.total_likes ?? data.count ?? likeCount.value + 1
}

function handleWsViewer(data: any) {
  viewerCount.value = data.count ?? data.viewers ?? data
}

// Danmaku
async function sendDanmaku() {
  const text = danmakuText.value.trim()
  if (!text) return
  try {
    await interactionApi.sendDanmaku(roomId.value, {
      content: text,
      color: '#333',
    })
    // Also send via WS for instant display
    ws.send('danmaku', { content: text, color: '#333' })
    danmakuText.value = ''
  } catch { /* handled by interceptor */ }
}

// Like
async function handleLike() {
  try {
    const data = await interactionApi.like(roomId.value)
    likeCount.value = data.total_likes
  } catch { /* handled */ }
}

// Gift
function selectGift(gift: GiftItem) {
  if (selectedGift.value === gift.id) {
    selectedGift.value = null
  } else {
    selectedGift.value = gift.id
    giftQuantity.value = 1
  }
}

async function handleSendGift() {
  if (!selectedGift.value) return
  try {
    await interactionApi.sendGift(roomId.value, {
      gift_id: selectedGift.value,
      quantity: giftQuantity.value,
    })
    ElMessage.success('礼物已送出')
  } catch { /* handled */ }
}

// Follow
async function toggleFollow() {
  if (!room.value) return
  try {
    if (isFollowing.value) {
      await userApi.unfollow(room.value.streamer_id)
      isFollowing.value = false
      ElMessage.success('已取消关注')
    } else {
      await userApi.follow(room.value.streamer_id)
      isFollowing.value = true
      ElMessage.success('已关注')
    }
  } catch { /* handled */ }
}

onUnmounted(() => {
  ws.offDanmaku(handleWsDanmaku)
  ws.offLike(handleWsLike)
  ws.offViewerUpdate(handleWsViewer)
})
</script>

<style scoped>
.room-page {
  padding: 16px;
  max-width: 1400px;
  margin: 0 auto;
}

.loading-wrap {
  padding: 40px;
}

.room-layout {
  display: flex;
  gap: 16px;
}

.player-area {
  flex: 1;
  min-width: 0;
}

.danmaku-area {
  width: 340px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* Player */
.player {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: #1a1a2e;
  border-radius: 8px;
  overflow: hidden;
}

.player-cover {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.player-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #666;
}

.player-placeholder p {
  margin-top: 16px;
  font-size: 18px;
}

/* Room meta */
.room-meta {
  padding: 12px 0;
}

.room-meta h2 {
  margin: 0 0 8px;
  font-size: 18px;
}

.room-meta-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.streamer-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.streamer-name {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

/* Action bar */
.action-bar {
  padding: 12px 0;
  border-top: 1px solid var(--el-border-color-lighter);
}

.gift-bar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.gift-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 12px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  min-width: 72px;
}

.gift-item:hover {
  border-color: var(--el-color-primary);
}

.gift-item.selected {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.gift-icon {
  font-size: 24px;
}

.gift-name {
  font-size: 12px;
  margin-top: 4px;
}

.gift-price {
  font-size: 11px;
  color: var(--el-color-warning);
  margin-top: 2px;
}

.action-buttons {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* Streamer card */
.streamer-card :deep(.el-card__body) {
  padding: 16px;
}

.streamer-profile {
  display: flex;
  gap: 12px;
}

.streamer-detail {
  flex: 1;
}

.s-name {
  font-weight: 600;
  margin: 0 0 4px;
}

.s-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.streamer-stats {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 12px;
}

/* Viewer card */
.viewer-card :deep(.el-card__body) {
  padding: 12px 16px;
  font-size: 14px;
}

/* Danmaku list */
.danmaku-list-card {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.danmaku-list-card :deep(.el-card__body) {
  flex: 1;
  padding: 0;
  overflow: hidden;
}

.danmaku-list {
  height: 360px;
  overflow-y: auto;
  padding: 12px;
}

.danmaku-item {
  padding: 4px 0;
  font-size: 14px;
  line-height: 1.6;
}

.dm-nickname {
  color: var(--el-color-primary);
  font-weight: 500;
}

.dm-empty {
  text-align: center;
  color: var(--el-text-color-placeholder);
  padding-top: 80px;
}

/* Danmaku input */
.danmaku-input {
  margin-top: 0;
}

.guest-tip {
  text-align: center;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  padding: 12px;
}

@media (max-width: 768px) {
  .room-layout {
    flex-direction: column;
  }
  .danmaku-area {
    width: 100%;
  }
}
</style>
