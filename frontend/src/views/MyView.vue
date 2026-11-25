<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
import { showFailToast } from 'vant'
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

const auth = useAuthStore()
const router = useRouter()

onMounted(async () => {
  try {
    await auth.loadMe()
  } catch (error) {
    showFailToast((error as Error).message)
  }
})

function logout() {
  auth.logout()
  router.replace('/login')
}
</script>

<template>
  <div class="page">
    <van-nav-bar title="我的" right-text="退出登录" @click-right="logout" />
    <div v-if="auth.user" class="card">
      <h3>{{ auth.user.name }}</h3>
      <p v-if="auth.user.department" class="muted department">{{ auth.user.department }}</p>
    </div>
    <van-cell-group inset>
      <van-cell title="练习记录" label="查看对练成绩、趋势与教练报告" icon="chat-o" is-link to="/history" />
      <van-cell title="考试记录" label="查看每次考试的总分、结果和答卷" icon="records-o" is-link to="/my/exams" />
    </van-cell-group>
    <van-cell-group v-if="auth.user?.is_admin" inset style="margin-top: 16px">
      <van-cell title="效果与成本统计" icon="bar-chart-o" is-link to="/overview" />
      <van-cell title="管理后台（建议用电脑打开）" icon="setting-o" is-link to="/admin" />
    </van-cell-group>
  </div>
</template>

<style scoped>
.department { margin: 0; }
</style>
