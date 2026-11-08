<script setup lang="ts">
import { api } from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { ScenarioCard } from '@/types'
import { showFailToast } from 'vant'
import { onMounted, ref } from 'vue'

const auth = useAuthStore()
const scenarios = ref<ScenarioCard[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    await auth.loadMe()
    scenarios.value = await api.scenarios()
  } catch (e) {
    showFailToast((e as Error).message)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="page">
    <div class="hero">
      <div class="hello">你好，{{ auth.user?.name || '同学' }}</div>
      <div class="sub">选一个客户，开口练 3 分钟</div>
    </div>

    <van-skeleton v-if="loading" :row="6" style="margin: 16px" />

    <router-link v-for="s in scenarios" :key="s.id" :to="`/scenario/${s.id}`" class="card scenario">
      <div class="row">
        <div class="avatar">{{ s.persona.name.slice(0, 1) }}</div>
        <div class="main">
          <div class="name">{{ s.name }}</div>
          <div class="muted">{{ s.persona.name }} · {{ s.persona.role }}</div>
        </div>
        <van-icon name="arrow" color="#c9cdd4" />
      </div>
      <p class="summary">{{ s.summary }}</p>
      <div class="meta">
        <van-rate :model-value="s.difficulty" readonly size="12" color="#ff7d00" void-color="#e5e6eb" />
        <span class="muted">约 {{ s.estimated_minutes }} 分钟</span>
        <van-tag v-for="t in s.tags" :key="t" plain type="primary">{{ t }}</van-tag>
      </div>
    </router-link>

    <van-empty v-if="!loading && !scenarios.length" description="暂无可用场景" />
  </div>
</template>

<style scoped>
.hero {
  padding: 28px 20px 18px;
  background: linear-gradient(135deg, #1f6feb, #5b9bff);
  color: #fff;
  border-radius: 0 0 20px 20px;
}
.hello {
  font-size: 22px;
  font-weight: 600;
}
.sub {
  margin-top: 6px;
  opacity: 0.85;
}
.scenario {
  display: block;
  color: inherit;
  text-decoration: none;
}
.row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: #e8f1ff;
  color: #1f6feb;
  font-size: 18px;
  font-weight: 600;
  line-height: 44px;
  text-align: center;
}
.main {
  flex: 1;
}
.name {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 2px;
}
.summary {
  margin: 10px 0;
  font-size: 14px;
  color: #4e5969;
}
.meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
