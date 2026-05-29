<template>
  <div class="admin-rooms-page">
    <h2>直播间管理</h2>

    <el-card shadow="never">
      <el-table :data="rooms" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="title" label="标题" min-width="150" />
        <el-table-column prop="streamer_nickname" label="主播" width="100" />
        <el-table-column label="分类" width="80">
          <template #default="{ row }">{{ categoryLabels[row.category] || row.category }}</template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)">{{ statusLabels[row.status] }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="current_viewers" label="在线" width="60" />
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <template v-if="row.status !== 'banned'">
              <el-button size="small" type="danger" @click="handleBan(row)">封禁</el-button>
            </template>
            <template v-else>
              <el-button size="small" type="success" @click="handleUnban(row)">解封</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="prev, pager, next"
          @current-change="fetchRooms"
        />
      </div>
    </el-card>

    <!-- Ban dialog -->
    <el-dialog v-model="banDialogVisible" title="封禁直播间" width="400px">
      <el-input v-model="banReason" type="textarea" placeholder="封禁原因" />
      <template #footer>
        <el-button @click="banDialogVisible = false">取消</el-button>
        <el-button type="danger" @click="confirmBan">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { adminApi } from '@/api'
import { categoryLabels, statusLabels } from '@/utils/format'
import { ElMessage } from 'element-plus'
import type { RoomListItem } from '@/types'

const rooms = ref<RoomListItem[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = 20
const total = ref(0)

const banDialogVisible = ref(false)
const banTarget = ref<RoomListItem | null>(null)
const banReason = ref('')

onMounted(() => fetchRooms())

async function fetchRooms() {
  loading.value = true
  try {
    const data = await adminApi.listAdminRooms({ page: page.value, page_size: pageSize })
    rooms.value = data.items
    total.value = data.total
  } catch { /* */ }
  finally { loading.value = false }
}

function statusTagType(status: string) {
  if (status === 'live') return 'danger'
  if (status === 'banned') return 'danger'
  return 'info'
}

function handleBan(room: RoomListItem) {
  banTarget.value = room
  banReason.value = ''
  banDialogVisible.value = true
}

async function confirmBan() {
  if (!banTarget.value) return
  try {
    await adminApi.banRoom(banTarget.value.id, banReason.value || '违规')
    ElMessage.success('已封禁')
    banDialogVisible.value = false
    fetchRooms()
  } catch { /* */ }
}

async function handleUnban(room: RoomListItem) {
  try {
    await adminApi.unbanRoom(room.id)
    ElMessage.success('已解封')
    fetchRooms()
  } catch { /* */ }
}
</script>

<style scoped>
.admin-rooms-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.admin-rooms-page h2 {
  margin: 0 0 20px;
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
</style>
