<template>
  <div class="admin-users-page">
    <h2>用户管理</h2>

    <el-card shadow="never">
      <el-table :data="users" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="username" label="用户名" width="120" />
        <el-table-column prop="nickname" label="昵称" width="120" />
        <el-table-column label="角色" width="80">
          <template #default="{ row }">{{ roleLabels[row.role] }}</template>
        </el-table-column>
        <el-table-column label="认证" width="80">
          <template #default="{ row }">
            <el-tag v-if="row.streamer_verified" type="success" size="small">已认证</el-tag>
            <el-tag v-else-if="row.role === 'streamer'" type="info" size="small">未认证</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_banned ? 'danger' : 'success'" size="small">
              {{ row.is_banned ? '已封禁' : '正常' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="注册时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <template v-if="!row.is_banned">
              <el-button size="small" type="danger" @click="handleBan(row)">封禁</el-button>
            </template>
            <template v-else>
              <el-button size="small" type="success" @click="handleUnban(row)">解封</el-button>
            </template>
            <el-button
              v-if="row.role === 'streamer' && !row.streamer_verified"
              size="small"
              type="warning"
              @click="handleVerify(row)"
            >
              认证
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="prev, pager, next"
          @current-change="fetchUsers"
        />
      </div>
    </el-card>

    <!-- Ban dialog -->
    <el-dialog v-model="banDialogVisible" title="封禁用户" width="400px">
      <el-form :model="banForm">
        <el-form-item label="封禁原因">
          <el-input v-model="banForm.reason" type="textarea" />
        </el-form-item>
        <el-form-item label="封禁时长(小时)">
          <el-input-number v-model="banForm.duration" :min="0" :max="8760" />
          <span style="margin-left:8px;color:#999">0=永久</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="banDialogVisible = false">取消</el-button>
        <el-button type="danger" :loading="banSubmitting" @click="confirmBan">确认封禁</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { adminApi } from '@/api'
import { formatTime, roleLabels } from '@/utils/format'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { AdminUserItem } from '@/types'

const users = ref<AdminUserItem[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = 20
const total = ref(0)

const banDialogVisible = ref(false)
const banSubmitting = ref(false)
const banTarget = ref<AdminUserItem | null>(null)
const banForm = ref({ reason: '', duration: 0 })

onMounted(() => fetchUsers())

async function fetchUsers() {
  loading.value = true
  try {
    const data = await adminApi.listUsers({ page: page.value, page_size: pageSize })
    users.value = data.items
    total.value = data.total
  } catch { /* */ }
  finally { loading.value = false }
}

function handleBan(user: AdminUserItem) {
  banTarget.value = user
  banForm.value = { reason: '', duration: 24 }
  banDialogVisible.value = true
}

async function confirmBan() {
  if (!banTarget.value) return
  banSubmitting.value = true
  try {
    await adminApi.banUser(banTarget.value.id, {
      reason: banForm.value.reason || '违规',
      duration_hours: banForm.value.duration,
    })
    ElMessage.success('已封禁')
    banDialogVisible.value = false
    fetchUsers()
  } catch { /* */ }
  finally { banSubmitting.value = false }
}

async function handleUnban(user: AdminUserItem) {
  try {
    await ElMessageBox.confirm(`确认解封用户 "${user.nickname}"？`, '解封确认')
    await adminApi.unbanUser(user.id)
    ElMessage.success('已解封')
    fetchUsers()
  } catch { /* cancelled */ }
}

async function handleVerify(user: AdminUserItem) {
  try {
    await ElMessageBox.confirm(`确认通过 "${user.nickname}" 的主播认证？`, '认证确认')
    await adminApi.verifyStreamer(user.id, { approved: true })
    ElMessage.success('认证已通过')
    fetchUsers()
  } catch { /* */ }
}
</script>

<style scoped>
.admin-users-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.admin-users-page h2 {
  margin: 0 0 20px;
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
</style>
