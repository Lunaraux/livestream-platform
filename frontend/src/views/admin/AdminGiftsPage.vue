<template>
  <div class="admin-gifts-page">
    <h2>礼物与弹幕管理</h2>

    <el-row :gutter="16">
      <!-- Existing gifts list -->
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>礼物列表</template>
          <el-table :data="gifts" stripe style="width:100%">
            <el-table-column prop="id" label="ID" width="60" />
            <el-table-column prop="icon" label="图标" width="80">
              <template #default="{ row }">
                <span style="font-size:24px">{{ row.icon }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="name" label="名称" width="100" />
            <el-table-column label="价格" width="100">
              <template #default="{ row }">¥{{ fenToYuan(row.price_fen) }}</template>
            </el-table-column>
            <el-table-column prop="effect" label="特效" />
          </el-table>
        </el-card>
      </el-col>

      <!-- Forbidden words -->
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <div class="header-row">
              <span>违禁词管理</span>
              <el-button size="small" type="primary" @click="showAddWordDialog = true">
                添加
              </el-button>
            </div>
          </template>
          <div class="word-list">
            <el-tag
              v-for="word in forbiddenWords"
              :key="word.id"
              closable
              class="word-tag"
              @close="deleteWord(word)"
            >
              {{ word.word }}
            </el-tag>
            <el-empty v-if="forbiddenWords.length === 0" description="暂无违禁词" :image-size="60" />
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Add word dialog -->
    <el-dialog v-model="showAddWordDialog" title="添加违禁词" width="400px">
      <el-input v-model="newWord" placeholder="输入违禁词" />
      <template #footer>
        <el-button @click="showAddWordDialog = false">取消</el-button>
        <el-button type="primary" @click="addWord">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { interactionApi, adminApi } from '@/api'
import { fenToYuan } from '@/utils/format'
import { ElMessage } from 'element-plus'
import type { GiftItem, ForbiddenWord } from '@/types'

const gifts = ref<GiftItem[]>([])
const forbiddenWords = ref<ForbiddenWord[]>([])
const showAddWordDialog = ref(false)
const newWord = ref('')

onMounted(() => {
  fetchGifts()
  fetchForbiddenWords()
})

async function fetchGifts() {
  try {
    gifts.value = await interactionApi.getGifts()
  } catch { /* */ }
}

async function fetchForbiddenWords() {
  try {
    forbiddenWords.value = await adminApi.listForbiddenWords()
  } catch { /* */ }
}

async function addWord() {
  if (!newWord.value.trim()) return
  try {
    await adminApi.addForbiddenWord(newWord.value.trim())
    ElMessage.success('添加成功')
    newWord.value = ''
    showAddWordDialog.value = false
    fetchForbiddenWords()
  } catch { /* */ }
}

async function deleteWord(word: ForbiddenWord) {
  try {
    await adminApi.deleteForbiddenWord(word.id)
    ElMessage.success('已删除')
    forbiddenWords.value = forbiddenWords.value.filter(w => w.id !== word.id)
  } catch { /* */ }
}
</script>

<style scoped>
.admin-gifts-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.admin-gifts-page h2 {
  margin: 0 0 20px;
}

.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.word-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-height: 80px;
}

.word-tag {
  margin: 0;
}
</style>
