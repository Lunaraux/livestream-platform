<template>
  <div class="profile-page">
    <h2>个人资料</h2>

    <el-card shadow="never" class="profile-card">
      <!-- Info display -->
      <div class="profile-header">
        <el-avatar :size="80" :src="form.avatar_url" />
        <div class="profile-summary">
          <h3>{{ auth.user?.nickname }}</h3>
          <p>
            <el-tag size="small">{{ roleLabels[auth.user?.role || 'audience'] }}</el-tag>
            <span style="margin-left:8px;font-size:13px;color:var(--el-text-color-secondary)">
              等级 {{ auth.user?.level || 1 }} · 注册于 {{ formatTime(auth.user?.created_at || '') }}
            </span>
          </p>
        </div>
      </div>

      <el-divider />

      <!-- Edit form -->
      <el-form :model="form" label-width="80px">
        <el-form-item label="昵称">
          <el-input v-model="form.nickname" maxlength="20" />
        </el-form-item>
        <el-form-item label="头像URL">
          <el-input v-model="form.avatar_url" placeholder="输入头像URL" />
        </el-form-item>
        <el-form-item label="个人简介">
          <el-input
            v-model="form.bio"
            type="textarea"
            :rows="3"
            maxlength="200"
            show-word-limit
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="saveProfile">
            保存修改
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Change password -->
    <el-card shadow="never" class="section-card">
      <template #header>修改密码</template>
      <el-form :model="pwForm" label-width="100px">
        <el-form-item label="原密码">
          <el-input v-model="pwForm.old_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="pwForm.new_password" type="password" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="pwSaving" @click="changePassword">
            修改密码
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Apply streamer -->
    <el-card v-if="auth.isStreamer && !auth.isVerifiedStreamer" shadow="never" class="section-card">
      <template #header>主播认证</template>
      <el-form :model="streamerForm" label-width="100px">
        <el-form-item label="真实姓名">
          <el-input v-model="streamerForm.real_name" />
        </el-form-item>
        <el-form-item label="身份证号">
          <el-input v-model="streamerForm.id_number" />
        </el-form-item>
        <el-form-item>
          <el-button type="warning" @click="applyStreamer">提交认证申请</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { userApi } from '@/api'
import { formatTime, roleLabels } from '@/utils/format'
import { ElMessage } from 'element-plus'

const auth = useAuthStore()
const saving = ref(false)

const form = reactive({
  nickname: auth.user?.nickname || '',
  avatar_url: auth.user?.avatar_url || '',
  bio: auth.user?.bio || '',
})

const pwForm = reactive({
  old_password: '',
  new_password: '',
})
const pwSaving = ref(false)

const streamerForm = reactive({
  real_name: '',
  id_number: '',
})

async function saveProfile() {
  saving.value = true
  try {
    await userApi.updateProfile({
      nickname: form.nickname || undefined,
      avatar_url: form.avatar_url || undefined,
      bio: form.bio || undefined,
    })
    // Refresh user info
    await auth.fetchMe()
    ElMessage.success('资料已更新')
  } catch { /* handled */ }
  finally { saving.value = false }
}

async function changePassword() {
  if (!pwForm.old_password || !pwForm.new_password) {
    ElMessage.warning('请填写原密码和新密码')
    return
  }
  pwSaving.value = true
  try {
    await userApi.changePassword({
      old_password: pwForm.old_password,
      new_password: pwForm.new_password,
    })
    ElMessage.success('密码修改成功')
    pwForm.old_password = ''
    pwForm.new_password = ''
  } catch { /* handled */ }
  finally { pwSaving.value = false }
}

async function applyStreamer() {
  if (!streamerForm.real_name || !streamerForm.id_number) {
    ElMessage.warning('请填写真实姓名和身份证号')
    return
  }
  try {
    await userApi.applyStreamer({
      real_name: streamerForm.real_name,
      id_number: streamerForm.id_number,
    })
    ElMessage.success('认证申请已提交')
  } catch { /* handled */ }
}
</script>

<style scoped>
.profile-page {
  max-width: 600px;
  margin: 0 auto;
  padding: 24px;
}

.profile-page h2 {
  margin: 0 0 20px;
}

.profile-card {
  margin-bottom: 20px;
}

.profile-header {
  display: flex;
  align-items: center;
  gap: 20px;
}

.profile-summary h3 {
  margin: 0 0 8px;
}

.profile-summary p {
  margin: 0;
}

.section-card {
  margin-bottom: 20px;
}
</style>
