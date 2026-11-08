<script setup lang="ts">
import { api } from '@/api'
import type { ScenarioDetail } from '@/types'
import { closeToast, showFailToast, showLoadingToast } from 'vant'
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const s = ref<ScenarioDetail | null>(null)

onMounted(async () => {
  try {
    s.value = await api.scenario(route.params.id as string)
  } catch (e) {
    showFailToast((e as Error).message)
  }
})

async function start() {
  if (!s.value) return
  showLoadingToast({ message: '客户正在接通…', forbidClick: true, duration: 0 })
  try {
    const session = await api.startSession(s.value.id)
    closeToast()
    router.replace(`/practice/${session.id}`)
  } catch (e) {
    showFailToast((e as Error).message)
  }
}
</script>

<template>
  <div class="page">
    <van-nav-bar title="场景说明" left-arrow @click-left="router.back()" />
    <template v-if="s">
      <div class="card">
        <h3>{{ s.name }}</h3>
        <van-rate :model-value="s.difficulty" readonly size="14" color="#ff7d00" void-color="#e5e6eb" />
        <p class="muted">约 {{ s.estimated_minutes }} 分钟 · 最多 {{ s.max_turns }} 轮</p>
      </div>
      <div class="card">
        <h3>客户：{{ s.persona.name }}（{{ s.persona.role }}）</h3>
        <p class="text">{{ s.persona.personality }}</p>
      </div>
      <div class="card">
        <h3>背景</h3>
        <p class="text">{{ s.background }}</p>
      </div>
      <div class="card goal">
        <h3>本次目标</h3>
        <p class="text">{{ s.goal }}</p>
        <p v-if="s.opening.tip" class="tip"><van-icon name="bulb-o" /> {{ s.opening.tip }}</p>
      </div>
      <div class="card">
        <h3>评分维度（{{ s.rubric.name }}）</h3>
        <div class="dims">
          <van-tag v-for="d in s.rubric.dimensions" :key="d.name" plain size="medium">{{ d.name }} {{ d.weight }}</van-tag>
        </div>
      </div>
      <div class="bottom">
        <p class="muted center">
          {{ s.opening.speaker === 'customer' ? '接通后客户会先开口' : '接通后由你先开口' }}
        </p>
        <van-button type="primary" block round size="large" @click="start">开始对练</van-button>
      </div>
    </template>
    <van-skeleton v-else :row="8" style="margin: 16px" />
  </div>
</template>

<style scoped>
.text {
  margin: 0;
  line-height: 1.7;
  white-space: pre-line;
  color: #4e5969;
  font-size: 14px;
}
.goal {
  border-left: 4px solid #1f6feb;
}
.tip {
  margin: 10px 0 0;
  padding: 8px 10px;
  background: #fff7e8;
  border-radius: 8px;
  color: #d25f00;
  font-size: 13px;
}
.dims {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.bottom {
  padding: 8px 16px 24px;
}
.center {
  text-align: center;
}
</style>
