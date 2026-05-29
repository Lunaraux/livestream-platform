<template>
  <el-container>
    <el-header height="60px" style="padding:0">
      <NavBar />
    </el-header>
    <el-main style="margin-top:60px; min-height:calc(100vh - 60px)">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import NavBar from './NavBar.vue'
</script>

<style>
body {
  margin: 0;
  background-color: var(--el-bg-color-page);
}
</style>
