<template>
  <AppLayout />
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import AppLayout from '@/layouts/AppLayout.vue'

const auth = useAuthStore()

onMounted(() => {
  auth.initFromStorage()
  if (auth.isLoggedIn) {
    auth.fetchMe()
  }
})
</script>
