<template>
  <div class="admin-withdraw-page">
    <h2>提现审核</h2>

    <el-card shadow="never">
      <el-table :data="withdraws" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column label="金额" width="120">
          <template #default="{ row }">¥{{ fenToYuan(row.amount_fen) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="申请时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="处理时间" width="170">
          <template #default="{ row }">{{ formatTime(row.processed_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <template v-if="row.status === 'pending'">
              <el-button size="small" type="success" @click="approve(row)">通过</el-button>
              <el-button size="small" type="danger" @click="reject(row)">拒绝</el-button>
            </template>
            <span v-else>-</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="prev, pager, next"
          @current-change="fetchWithdraws"
        />
      </div>
    </el-card>

    <!-- Reject dialog -->
    <el-dialog v-model="rejectDialogVisible" title="拒绝提现" width="400px">
      <el-input v-model="rejectReason" type="textarea" placeholder="拒绝原因" />
      <template #footer>
        <el-button @click="rejectDialogVisible = false">取消</el-button>
        <el-button type="danger" @click="confirmReject">确认拒绝</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { adminApi } from '@/api'
import { fenToYuan, formatTime } from '@/utils/format'
import { ElMessage } from 'element-plus'
import type { WithdrawRecord } from '@/types'

const withdraws = ref<WithdrawRecord[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = 20
const total = ref(0)

const rejectDialogVisible = ref(false)
const rejectTarget = ref<WithdrawRecord | null>(null)
const rejectReason = ref('')

onMounted(() => fetchWithdraws())

async function fetchWithdraws() {
  loading.value = true
  try {
    const data = await adminApi.listWithdraws({ page: page.value, page_size: pageSize })
    withdraws.value = data.items
    total.value = data.total
  } catch { /* */ }
  finally { loading.value = false }
}

function statusType(status: string) {
  return status === 'approved' ? 'success' : status === 'rejected' ? 'danger' : 'warning'
}
function statusLabel(status: string) {
  return status === 'approved' ? '已通过' : status === 'rejected' ? '已拒绝' : '待审核'
}

async function approve(item: WithdrawRecord) {
  try {
    await adminApi.approveWithdraw(item.id)
    ElMessage.success('已通过')
    fetchWithdraws()
  } catch { /* */ }
}

function reject(item: WithdrawRecord) {
  rejectTarget.value = item
  rejectReason.value = ''
  rejectDialogVisible.value = true
}

async function confirmReject() {
  if (!rejectTarget.value) return
  try {
    await adminApi.rejectWithdraw(rejectTarget.value.id, rejectReason.value || '审核不通过')
    ElMessage.success('已拒绝')
    rejectDialogVisible.value = false
    fetchWithdraws()
  } catch { /* */ }
}
</script>

<style scoped>
.admin-withdraw-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.admin-withdraw-page h2 {
  margin: 0 0 20px;
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
</style>
