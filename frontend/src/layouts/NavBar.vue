<template>
  <el-menu
    mode="horizontal"
    :ellipsis="false"
    class="navbar"
    router
  >
    <el-menu-item index="/">
      <el-icon :size="22"><VideoCamera /></el-icon>
      <span class="brand">LiveStream</span>
    </el-menu-item>

    <div class="flex-grow" />

    <!-- Search -->
    <div class="search-box">
      <el-input
        v-model="searchQuery"
        placeholder="搜索直播间..."
        size="default"
        clearable
        @keyup.enter="doSearch"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
    </div>

    <!-- Guest links -->
    <template v-if="!auth.isLoggedIn">
      <el-menu-item index="/login">登录</el-menu-item>
      <el-menu-item index="/register">注册</el-menu-item>
    </template>

    <!-- Logged in links -->
    <template v-if="auth.isLoggedIn">
      <el-sub-menu index="user-menu">
        <template #title>
          <el-avatar :size="28" :src="auth.user?.avatar_url" />
          <span style="margin-left:8px">{{ auth.user?.nickname }}</span>
        </template>
        <el-menu-item index="/profile">
          <el-icon><User /></el-icon>个人资料
        </el-menu-item>
        <el-menu-item index="/wallet">
          <el-icon><Wallet /></el-icon>我的钱包
        </el-menu-item>
        <el-menu-item index="/following">
          <el-icon><Star /></el-icon>我的关注
        </el-menu-item>

        <!-- Streamer submenu -->
        <template v-if="auth.isStreamer || auth.isAdmin">
          <el-divider style="margin:4px 0" />
          <el-menu-item index="/streamer/room">
            <el-icon><Setting /></el-icon>直播间管理
          </el-menu-item>
          <el-menu-item index="/streamer/live">
            <el-icon><VideoPlay /></el-icon>开播控制台
          </el-menu-item>
          <el-menu-item index="/streamer/earnings">
            <el-icon><Money /></el-icon>收益中心
          </el-menu-item>
          <el-menu-item index="/streamer/dashboard">
            <el-icon><DataAnalysis /></el-icon>数据大屏
          </el-menu-item>
        </template>

        <!-- Admin submenu -->
        <template v-if="auth.isAdmin">
          <el-divider style="margin:4px 0" />
          <el-menu-item index="/admin/dashboard">
            <el-icon><Monitor /></el-icon>平台管理
          </el-menu-item>
        </template>

        <el-divider style="margin:4px 0" />
        <el-menu-item @click="auth.logout()">
          <el-icon><SwitchButton /></el-icon>退出登录
        </el-menu-item>
      </el-sub-menu>
    </template>
  </el-menu>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import {
  VideoCamera, Search, User, Wallet, Star, Setting,
  VideoPlay, Money, DataAnalysis, Monitor, SwitchButton,
} from '@element-plus/icons-vue'

const auth = useAuthStore()
const router = useRouter()
const searchQuery = ref('')

function doSearch() {
  if (searchQuery.value.trim()) {
    router.push({ path: '/', query: { q: searchQuery.value.trim() } })
    searchQuery.value = ''
  }
}
</script>

<style scoped>
.navbar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  height: 60px;
  padding: 0 16px;
  border-bottom: 1px solid var(--el-border-color-light);
}

.brand {
  font-weight: 700;
  font-size: 18px;
  margin-left: 8px;
}

.flex-grow {
  flex: 1;
}

.search-box {
  width: 280px;
  margin-right: 16px;
}
</style>
