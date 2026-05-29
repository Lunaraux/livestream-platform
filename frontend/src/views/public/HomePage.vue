<template>
  <div class="home-page">
    <!-- Hero -->
    <section v-if="!searchQuery" class="hero">
      <h2>热门推荐</h2>
      <div class="room-grid">
        <el-card
          v-for="room in recommended"
          :key="room.id"
          :body-style="{ padding: '0' }"
          shadow="hover"
          class="room-card"
          @click="goRoom(room.id)"
        >
          <div class="room-cover">
            <img :src="room.cover_url || '/default-cover.jpg'" :alt="room.title" />
            <el-tag type="danger" size="small" class="live-badge">LIVE</el-tag>
            <span class="viewers">{{ room.current_viewers }} 人在看</span>
          </div>
          <div class="room-info">
            <p class="room-title">{{ room.title }}</p>
            <p class="room-streamer">
              <el-avatar :size="20" :src="room.streamer_avatar" />
              {{ room.streamer_nickname }}
            </p>
            <el-tag size="small" type="info">{{ categoryLabels[room.category] || room.category }}</el-tag>
          </div>
        </el-card>
      </div>
    </section>

    <!-- Room list -->
    <section>
      <div class="section-header">
        <h2>{{ searchQuery ? `搜索："${searchQuery}"` : '正在直播' }}</h2>
        <div class="filters">
          <el-select v-model="category" placeholder="全部分类" clearable style="width:120px">
            <el-option
              v-for="(label, key) in categoryLabels"
              :key="key"
              :label="label"
              :value="key"
            />
          </el-select>
          <el-select v-model="sortBy" style="width:120px">
            <el-option label="按热度" value="viewers" />
            <el-option label="按时间" value="time" />
          </el-select>
        </div>
      </div>

      <div v-if="rooms.length === 0" class="empty-state">
        <el-empty description="暂无直播中的房间" />
      </div>

      <div v-else class="room-grid">
        <el-card
          v-for="room in rooms"
          :key="room.id"
          :body-style="{ padding: '0' }"
          shadow="hover"
          class="room-card"
          @click="goRoom(room.id)"
        >
          <div class="room-cover">
            <img :src="room.cover_url || '/default-cover.jpg'" :alt="room.title" />
            <el-tag type="danger" size="small" class="live-badge">LIVE</el-tag>
            <span class="viewers">{{ room.current_viewers }} 人在看</span>
          </div>
          <div class="room-info">
            <p class="room-title">{{ room.title }}</p>
            <p class="room-streamer">
              <el-avatar :size="20" :src="room.streamer_avatar" />
              {{ room.streamer_nickname }}
            </p>
            <el-tag size="small" type="info">{{ categoryLabels[room.category] || room.category }}</el-tag>
          </div>
        </el-card>
      </div>

      <!-- Pagination -->
      <div v-if="total > pageSize" class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="prev, pager, next"
          @current-change="fetchRooms"
        />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { roomApi } from '@/api'
import { categoryLabels } from '@/utils/format'
import type { RoomListItem } from '@/types'

const route = useRoute()
const router = useRouter()

const recommended = ref<RoomListItem[]>([])
const rooms = ref<RoomListItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const category = ref<string | undefined>()
const sortBy = ref('viewers')
const searchQuery = ref('')

// Watch query params for search
watch(() => route.query.q, (val) => {
  searchQuery.value = (val as string) || ''
  page.value = 1
  fetchRooms()
})

watch([category, sortBy], () => {
  page.value = 1
  fetchRooms()
})

async function fetchRecommended() {
  try {
    recommended.value = await roomApi.recommended()
  } catch { /* ignore */ }
}

async function fetchRooms() {
  try {
    if (searchQuery.value) {
      const data = await roomApi.search(searchQuery.value, page.value, pageSize)
      rooms.value = data.items
      total.value = data.total
    } else {
      const data = await roomApi.list({
        page: page.value,
        page_size: pageSize,
        category: category.value,
        sort_by: sortBy.value,
      })
      rooms.value = data.items
      total.value = data.total
    }
  } catch { /* ignore */ }
}

function goRoom(id: number) {
  router.push(`/rooms/${id}`)
}

onMounted(() => {
  if (route.query.q) {
    searchQuery.value = route.query.q as string
  }
  fetchRecommended()
  fetchRooms()
})
</script>

<style scoped>
.home-page {
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px;
}

.hero {
  margin-bottom: 32px;
}

.hero h2 {
  font-size: 20px;
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-header h2 {
  font-size: 20px;
  margin: 0;
}

.filters {
  display: flex;
  gap: 8px;
}

.room-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.room-card {
  cursor: pointer;
  transition: transform 0.2s;
}

.room-card:hover {
  transform: translateY(-2px);
}

.room-cover {
  position: relative;
  height: 160px;
  overflow: hidden;
}

.room-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  background: var(--el-fill-color-dark);
}

.live-badge {
  position: absolute;
  top: 8px;
  left: 8px;
}

.viewers {
  position: absolute;
  bottom: 8px;
  right: 8px;
  color: white;
  font-size: 12px;
  background: rgba(0, 0, 0, 0.6);
  padding: 2px 8px;
  border-radius: 4px;
}

.room-info {
  padding: 12px;
}

.room-title {
  font-weight: 600;
  font-size: 14px;
  margin: 0 0 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.room-streamer {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 0 0 8px;
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}

.empty-state {
  padding: 60px 0;
}
</style>
