<script setup lang="ts">
import { api } from '@/api'
import type { PaperCard } from '@/types'
import { scoreColor } from '@/utils/labels'
import { closeToast, showFailToast, showLoadingToast } from 'vant'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const papers = ref<PaperCard[]>([])
const loading = ref(true)
const starting = ref(false)

onMounted(async () => {
  try {
    papers.value = await api.papers()
  } catch (e) {
    showFailToast((e as Error).message)
  } finally {
    loading.value = false
  }
})

const SECTION_ICON: Record<string, string> = { quiz: 'edit', listening: 'service-o', roleplay: 'user-o' }

async function start(p: PaperCard) {
  if (starting.value) return
  starting.value = true
  showLoadingToast({ message: '正在生成试卷…', duration: 0, forbidClick: true })
  try {
    const a = await api.startExam(p.id)
    closeToast()
    await router.push(`/attempt/${a.id}`)
  } catch (e) {
    closeToast()
    showFailToast((e as Error).message)
  } finally {
    starting.value = false
  }
}
</script>

<template>
  <div class="page">
    <van-nav-bar title="考试与自测" />
    <van-skeleton v-if="loading" :row="6" style="margin: 16px" />

    <div v-for="p in papers" :key="p.id" class="card paper">
      <div class="head">
        <van-tag :type="p.kind === 'exam' ? 'danger' : 'primary'">{{ p.kind === 'exam' ? '正式考试' : '自测' }}</van-tag>
        <span class="name">{{ p.name }}</span>
      </div>
      <p class="muted">{{ p.description }}</p>
      <div class="sections">
        <span v-for="s in p.sections" :key="s.title" class="sec">
          <van-icon :name="SECTION_ICON[s.type]" /> {{ s.title }}
        </span>
      </div>
      <div class="foot">
        <span class="muted">
          及格 {{ p.pass_score }} 分
          <template v-if="p.time_limit_minutes"> · {{ p.time_limit_minutes }} 分钟</template>
          <template v-if="p.max_attempts"> · 限 {{ p.max_attempts }} 次</template>
        </span>
        <span v-if="p.attempts" class="muted">
          已考 {{ p.attempts }} 次
          <template v-if="p.best_score !== null">
            · 最高 <b :style="{ color: scoreColor(p.best_score) }">{{ p.best_score }}</b>
          </template>
          <van-tag v-if="p.passed" type="success" style="margin-left: 4px">已通过</van-tag>
        </span>
      </div>
      <van-button
        type="primary"
        block
        round
        style="margin-top: 10px"
        :plain="p.kind !== 'exam'"
        :disabled="!!p.max_attempts && p.attempts >= p.max_attempts && !p.ongoing_attempt_id"
        @click="start(p)"
      >
        {{ p.ongoing_attempt_id ? '继续作答' : p.kind === 'exam' ? '开始考试' : '开始练习' }}
      </van-button>
    </div>

    <van-empty v-if="!loading && !papers.length" description="暂无试卷" />
  </div>
</template>

<style scoped>
.head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.name {
  font-size: 16px;
  font-weight: 600;
}
.sections {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 8px 0;
  font-size: 13px;
  color: #4e5969;
}
.foot {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
}
</style>
