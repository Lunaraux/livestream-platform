<template>
  <div class="room-manage-page">
    <h2>直播间管理</h2>

    <!-- No room yet -->
    <div v-if="!room" class="create-section">
      <el-empty description="你还没有创建直播间">
        <el-button type="primary" @click="showCreateDialog = true">创建直播间</el-button>
      </el-empty>
    </div>

    <!-- Room exists -->
    <template v-else>
      <el-card shadow="never" class="room-card">
        <div class="room-info-header">
          <img
            v-if="room.cover_url"
            :src="room.cover_url"
            class="room-cover"
          />
          <div class="room-info-detail">
            <h3>{{ room.title }}</h3>
            <p>{{ room.description || '暂无简介' }}</p>
            <div class="room-tags">
              <el-tag>{{ categoryLabels[room.category] || room.category }}</el-tag>
              <el-tag :type="statusType">{{ statusLabels[room.status] }}</el-tag>
            </div>
            <div class="room-stats">
              <span>直播次数：{{ room.total_sessions }}</span>
              <span>峰值观众：{{ room.peak_viewers }}</span>
            </div>
          </div>
        </div>

        <el-divider />

        <div class="room-actions">
          <el-button
            v-if="room.status === 'idle'"
            type="success"
            @click="startStream"
          >
            开始直播
          </el-button>
          <el-button
            v-if="room.status === 'live'"
            type="danger"
            @click="endStream"
          >
            结束直播
          </el-button>
          <el-button type="primary" @click="showEditDialog = true">
            编辑信息
          </el-button>
        </div>
      </el-card>
    </template>

    <!-- Create/edit dialog -->
    <el-dialog
      v-model="showCreateDialog"
      :title="room ? '编辑直播间' : '创建直播间'"
      width="500px"
    >
      <el-form :model="roomForm" label-width="80px">
        <el-form-item label="标题" required>
          <el-input v-model="roomForm.title" maxlength="30" />
        </el-form-item>
        <el-form-item label="分类" required>
          <el-select v-model="roomForm.category" style="width:100%">
            <el-option
              v-for="(label, key) in categoryLabels"
              :key="key"
              :label="label"
              :value="key"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="简介">
          <el-input
            v-model="roomForm.description"
            type="textarea"
            :rows="3"
            maxlength="200"
          />
        </el-form-item>
        <el-form-item label="封面URL">
          <el-input v-model="roomForm.cover_url" placeholder="输入封面图URL" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveRoom">
          {{ room ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- Edit dialog (reuses form) -->
    <el-dialog
      v-model="showEditDialog"
      title="编辑直播间"
      width="500px"
    >
      <el-form :model="roomForm" label-width="80px">
        <el-form-item label="标题" required>
          <el-input v-model="roomForm.title" maxlength="30" />
        </el-form-item>
        <el-form-item label="分类" required>
          <el-select v-model="roomForm.category" style="width:100%">
            <el-option v-for="(label, key) in categoryLabels" :key="key" :label="label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="roomForm.description" type="textarea" :rows="3" maxlength="200" />
        </el-form-item>
        <el-form-item label="封面URL">
          <el-input v-model="roomForm.cover_url" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="updateRoom">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { roomApi } from '@/api'
import { categoryLabels, statusLabels } from '@/utils/format'
import { ElMessage } from 'element-plus'
import type { RoomResponse } from '@/types'

const room = ref<RoomResponse | null>(null)
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const saving = ref(false)

const roomForm = reactive({
  title: '',
  description: '',
  category: 'chat',
  cover_url: '',
})

const statusType = computed(() => {
  if (room.value?.status === 'live') return 'danger'
  if (room.value?.status === 'banned') return 'danger'
  if (room.value?.status === 'ended') return 'info'
  return 'success'
})

onMounted(() => fetchRoom())

async function fetchRoom() {
  try {
    // Load room via streamer's own endpoint; using room list with streamer filter
    const data = await roomApi.list()
    const myRooms = data.items.filter((r: any) => r.status !== 'ended')
    if (myRooms.length > 0) {
      room.value = await roomApi.detail(myRooms[0].id)
    }
  } catch { /* no room */ }
}

async function saveRoom() {
  if (!roomForm.title) {
    ElMessage.warning('请输入直播间标题')
    return
  }
  saving.value = true
  try {
    room.value = await roomApi.create({
      title: roomForm.title,
      description: roomForm.description || undefined,
      category: roomForm.category,
      cover_url: roomForm.cover_url || undefined,
    })
    ElMessage.success('直播间创建成功')
    showCreateDialog.value = false
  } catch { /* handled */ }
  finally { saving.value = false }
}

async function updateRoom() {
  if (!room.value) return
  saving.value = true
  try {
    room.value = await roomApi.update(room.value.id, {
      title: roomForm.title,
      description: roomForm.description || undefined,
      category: roomForm.category,
      cover_url: roomForm.cover_url || undefined,
    })
    ElMessage.success('更新成功')
    showEditDialog.value = false
  } catch { /* handled */ }
  finally { saving.value = false }
}

function openEdit() {
  if (!room.value) return
  roomForm.title = room.value.title
  roomForm.description = room.value.description || ''
  roomForm.category = room.value.category
  roomForm.cover_url = room.value.cover_url || ''
  showEditDialog.value = true
}

// Override showEditDialog behavior
watch(showEditDialog, (val) => {
  if (val) openEdit()
})

async function startStream() {
  if (!room.value) return
  try {
    room.value = await roomApi.start(room.value.id)
    ElMessage.success('开播成功')
  } catch { /* handled */ }
}

async function endStream() {
  if (!room.value) return
  try {
    const stats = await roomApi.end(room.value.id)
    ElMessage.success(`直播已结束，峰值${stats.peak_viewers}人`)
    fetchRoom()
  } catch { /* handled */ }
}
</script>

<style scoped>
.room-manage-page {
  max-width: 800px;
  margin: 0 auto;
  padding: 24px;
}

.room-manage-page h2 {
  margin: 0 0 20px;
}

.room-info-header {
  display: flex;
  gap: 20px;
}

.room-cover {
  width: 240px;
  height: 135px;
  object-fit: cover;
  border-radius: 8px;
  background: var(--el-fill-color-dark);
}

.room-info-detail {
  flex: 1;
}

.room-info-detail h3 {
  margin: 0 0 8px;
}

.room-info-detail p {
  color: var(--el-text-color-secondary);
  margin: 0 0 12px;
}

.room-tags {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.room-stats {
  display: flex;
  gap: 20px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.room-actions {
  display: flex;
  gap: 12px;
}

.create-section {
  padding: 60px 0;
}
</style>
