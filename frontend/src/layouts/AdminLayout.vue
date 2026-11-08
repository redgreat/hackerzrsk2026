<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const active = computed(() => route.path)

const menus = [
  { path: '/admin', label: '数据概览' },
  { path: '/admin/sessions', label: '练习记录' },
  { path: '/admin/users', label: '员工' },
  { path: '/admin/usage', label: '模型用量' },
  { path: '/admin/scenarios', label: '场景配置' },
  { path: '/admin/knowledge', label: '话术知识库' },
]

function logout() {
  auth.logout()
  router.replace('/login')
}
</script>

<template>
  <el-container class="admin">
    <el-aside width="200px" class="aside">
      <div class="brand">AI 客户陪练<span>管理后台</span></div>
      <el-menu :default-active="active" router background-color="#001529" text-color="#c0c4cc" active-text-color="#fff">
        <el-menu-item v-for="m in menus" :key="m.path" :index="m.path">{{ m.label }}</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span class="muted">{{ route.meta.title }}</span>
        <div class="right">
          <router-link to="/">返回练习端</router-link>
          <span>{{ auth.user?.name || auth.user?.userid }}</span>
          <el-link type="danger" :underline="false" @click="logout">退出</el-link>
        </div>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.admin {
  min-height: 100vh;
  background: #f0f2f5;
}
.aside {
  background: #001529;
}
.brand {
  height: 56px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 0 20px;
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  line-height: 1.3;
}
.brand span {
  font-size: 12px;
  font-weight: 400;
  opacity: 0.6;
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e5e6eb;
  height: 56px;
}
.right {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 14px;
}
.main {
  padding: 20px;
}
.muted {
  color: #86909c;
}
</style>
