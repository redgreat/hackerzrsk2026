<script setup lang="ts">
import { api } from '@/api'
import LineTrend from '@/components/LineTrend.vue'
import type { MyStats, SessionSummary } from '@/types'
import { OUTCOME_LABEL, OUTCOME_TAG, formatTime, scoreColor } from '@/utils/labels'
import { showFailToast } from 'vant'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const stats = ref<MyStats | null>(null)
const sessions = ref<SessionSummary[]>([])
const loading = ref(false)
const loadError = ref('')
const hasMore = ref(false)
const pageSize = 30

async function load() {
  if (loading.value) return
  loading.value = true
  loadError.value = ''
  try {
    const page = await api.sessions(sessions.value.length, pageSize + 1)
    sessions.value.push(...page.slice(0, pageSize))
    hasMore.value = page.length > pageSize
  } catch (error) {
    loadError.value = (error as Error).message
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  void load()
  try {
    stats.value = await api.myStats()
  } catch (error) {
    showFailToast((error as Error).message)
  }
})

function open(s: SessionSummary) {
  router.push(s.status === 'ongoing' ? `/practice/${s.id}` : `/report/${s.id}`)
}

</script>

<template>
  <div class="page">
    <van-nav-bar title="练习记录" left-arrow @click-left="router.push('/my')" />
    <p class="page-guide">查看自己的练习成绩和待提升能力，点开一条已完成的练习可回看报告。</p>

    <div v-if="stats" class="card summary">
      <div>
        <b>{{ stats.practice_count }}</b>
        <span class="muted">完成练习</span>
      </div>
      <div>
        <b :style="{ color: scoreColor(stats.avg_score) }">{{ stats.avg_score ?? '-' }}</b>
        <span class="muted">平均分</span>
      </div>
      <div>
        <b :style="{ color: scoreColor(stats.best_score) }">{{ stats.best_score ?? '-' }}</b>
        <span class="muted">最高分</span>
      </div>
    </div>

    <div v-if="stats && stats.trend.length > 1" class="card">
      <h3>分数趋势</h3>
      <LineTrend :values="stats.trend.map((t) => t.score)" :labels="stats.trend.map((t) => formatTime(t.date).split(' ')[0])" />
    </div>

    <div v-if="stats && stats.dimension_avg.length" class="card">
      <h3>待加强的能力</h3>
      <div v-for="d in stats.dimension_avg.slice(0, 3)" :key="d.name" class="weak">
        <span>{{ d.name }}</span>
        <van-progress :percentage="(d.avg / 5) * 100" :show-pivot="false" stroke-width="6" color="#ff7d00" />
        <span class="muted">{{ d.avg }}</span>
      </div>
    </div>

    <van-skeleton v-if="loading && !sessions.length" :row="5" style="margin: 16px" />
    <van-cell-group v-if="sessions.length" inset>
      <van-cell v-for="s in sessions" :key="s.id" is-link @click="open(s)">
        <template #title>
          <span>{{ s.scenario_name }}</span>
          <van-tag :type="OUTCOME_TAG[s.status]" style="margin-left: 6px">{{ OUTCOME_LABEL[s.status] }}</van-tag>
        </template>
        <template #label>{{ formatTime(s.started_at) }} · {{ s.turns }} 轮</template>
        <template #value>
          <b :style="{ color: scoreColor(s.total_score), fontSize: '18px' }">{{ s.total_score ?? '-' }}</b>
        </template>
      </van-cell>
    </van-cell-group>
    <van-empty v-if="!loading && !sessions.length && !loadError" description="还没有练习记录">
      <van-button type="primary" round to="/">去练习</van-button>
    </van-empty>
    <div v-if="hasMore || loadError" class="more">
      <p v-if="loadError" class="muted" role="status">{{ loadError }}</p>
      <van-button plain size="small" :loading="loading" @click="load">{{ loadError ? '重试' : '加载更多' }}</van-button>
    </div>
  </div>
</template>

<style scoped>
.more { margin: 18px 16px; text-align: center; }
.summary {
  display: flex;
  justify-content: space-around;
  text-align: center;
}
.summary div {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.summary b {
  font-size: 24px;
}
.weak {
  display: grid;
  grid-template-columns: 110px 1fr 36px;
  align-items: center;
  gap: 8px;
  margin: 8px 0;
  font-size: 14px;
}
</style>
