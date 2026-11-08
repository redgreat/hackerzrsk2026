<script setup lang="ts">
import { api } from '@/api'
import LineTrend from '@/components/LineTrend.vue'
import { useAuthStore } from '@/stores/auth'
import type { MyStats, SessionSummary } from '@/types'
import { OUTCOME_LABEL, OUTCOME_TAG, formatTime, scoreColor } from '@/utils/labels'
import { showFailToast } from 'vant'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const auth = useAuthStore()
const stats = ref<MyStats | null>(null)
const sessions = ref<SessionSummary[]>([])

onMounted(async () => {
  try {
    await auth.loadMe()
    ;[stats.value, sessions.value] = await Promise.all([api.myStats(), api.sessions()])
  } catch (e) {
    showFailToast((e as Error).message)
  }
})

function open(s: SessionSummary) {
  router.push(s.status === 'ongoing' ? `/practice/${s.id}` : `/report/${s.id}`)
}

function logout() {
  auth.logout()
  router.replace('/login')
}
</script>

<template>
  <div class="page">
    <van-nav-bar title="我的练习">
      <template #right><span class="muted" @click="logout">退出</span></template>
    </van-nav-bar>

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

    <div class="section-title">练习记录</div>
    <van-cell-group inset>
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
    <van-empty v-if="!sessions.length" description="还没有练习记录，去练一次吧" />

    <van-cell-group inset style="margin-top: 16px">
      <van-cell v-if="auth.user?.is_admin" title="效果与成本统计" icon="bar-chart-o" is-link to="/overview" />
      <van-cell v-if="auth.user?.is_admin" title="管理后台（建议用电脑打开）" icon="setting-o" is-link to="/admin" />
    </van-cell-group>
  </div>
</template>

<style scoped>
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
