<template>
  <div class="following-page">
    <h2>我的关注</h2>

    <div v-if="following.length === 0" class="empty">
      <el-empty description="还没有关注任何主播" />
    </div>

    <div v-else class="following-list">
      <div v-for="item in following" :key="item.id" class="following-item">
        <el-avatar :size="48" :src="item.avatar_url" />
        <div class="f-info">
          <p class="f-name">{{ item.nickname }}</p>
          <p class="f-time">关注于 {{ formatTime(item.followed_at) }}</p>
        </div>
        <el-button size="small" @click="unfollow(item)">取消关注</el-button>
      </div>
    </div>

    <div v-if="total > pageSize" class="pagination-wrap">
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next"
        @current-change="fetchFollowing"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { userApi } from '@/api'
import { formatTime } from '@/utils/format'
import { ElMessage } from 'element-plus'
import type { FollowingItem } from '@/types'

const following = ref<FollowingItem[]>([])
const page = ref(1)
const pageSize = 20
const total = ref(0)

onMounted(() => fetchFollowing())

async function fetchFollowing() {
  try {
    const data = await userApi.getFollowing(page.value, pageSize)
    following.value = data.items
    total.value = data.total
  } catch { /* ignore */ }
}

async function unfollow(item: FollowingItem) {
  try {
    await userApi.unfollow(item.id)
    ElMessage.success('已取消关注')
    following.value = following.value.filter(f => f.id !== item.id)
  } catch { /* ignore */ }
}
</script>

<style scoped>
.following-page {
  max-width: 800px;
  margin: 0 auto;
  padding: 24px;
}

.following-page h2 {
  margin: 0 0 20px;
}

.following-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.following-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  background: var(--el-bg-color);
  border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

.f-info {
  flex: 1;
}

.f-name {
  font-weight: 600;
  margin: 0 0 4px;
}

.f-time {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 0;
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}

.empty {
  padding: 60px 0;
}
</style>
