<script setup lang="ts">
import { api } from '@/api'
import type { Overview } from '@/types'
import { showFailToast } from 'vant'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const data = ref<Overview | null>(null)

const PURPOSE: Record<string, string> = {
  customer: '客户回复',
  evaluator: '轮次评估',
  coach: '教练报告',
  hint: '求助提示',
  embedding: '知识向量',
  asr: '语音识别',
  tts: '语音合成',
}

onMounted(async () => {
  try {
    data.value = await api.overview()
  } catch (e) {
    showFailToast((e as Error).message)
  }
})

const pct = (v: number | null) => (v == null ? '-' : `${(v * 100).toFixed(1)}%`)
</script>

<template>
  <div class="page">
    <van-nav-bar title="效果与成本" left-arrow @click-left="router.back()" />
    <template v-if="data">
      <van-grid :column-num="3" :border="false" class="card grid">
        <van-grid-item :text="'完成练习'"><b>{{ data.finished_sessions }}</b></van-grid-item>
        <van-grid-item :text="'参与人数'"><b>{{ data.users }}</b></van-grid-item>
        <van-grid-item :text="'平均分'"><b>{{ data.avg_score ?? '-' }}</b></van-grid-item>
        <van-grid-item :text="'成功推进率'"><b>{{ pct(data.deal_rate) }}</b></van-grid-item>
        <van-grid-item :text="'平均轮数'"><b>{{ data.avg_turns ?? '-' }}</b></van-grid-item>
        <van-grid-item :text="'平均时长'">
          <b>{{ data.avg_duration_seconds ? `${Math.round(data.avg_duration_seconds / 60)}分` : '-' }}</b>
        </van-grid-item>
      </van-grid>

      <div class="card">
        <h3>成本对比</h3>
        <div class="cost">
          <div>
            <b>¥{{ data.avg_cost_yuan.toFixed(3) }}</b>
            <span class="muted">AI 陪练 / 次</span>
          </div>
          <div class="vs">vs</div>
          <div>
            <b>¥{{ data.manual_coaching_cost_yuan }}</b>
            <span class="muted">人工带教 / 次</span>
          </div>
        </div>
        <p class="saving">成本降低 <b>{{ pct(data.cost_saving_ratio) }}</b>，累计模型费用 ¥{{ data.total_cost_yuan.toFixed(2) }}</p>
      </div>

      <div class="card">
        <h3>调用明细</h3>
        <table>
          <thead>
            <tr><th>用途</th><th>次数</th><th>Token(入/出)</th><th>费用</th><th>耗时</th></tr>
          </thead>
          <tbody>
            <tr v-for="p in data.by_purpose" :key="p.purpose">
              <td>{{ PURPOSE[p.purpose] ?? p.purpose }}</td>
              <td>{{ p.calls }}</td>
              <td>{{ p.prompt_tokens }}/{{ p.completion_tokens }}</td>
              <td>¥{{ p.cost_yuan.toFixed(3) }}</td>
              <td>{{ p.avg_latency_ms }}ms</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card">
        <h3>场景练习情况</h3>
        <van-cell v-for="s in data.by_scenario" :key="s.scenario" :title="s.scenario" :value="`${s.count} 次 · 均分 ${s.avg_score ?? '-'}`" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.grid b {
  font-size: 20px;
  color: #1f6feb;
}
.cost {
  display: flex;
  justify-content: space-around;
  align-items: center;
  text-align: center;
}
.cost div {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.cost b {
  font-size: 22px;
}
.vs {
  color: #c9cdd4;
}
.saving {
  margin: 12px 0 0;
  text-align: center;
  font-size: 14px;
}
.saving b {
  color: #00b42a;
  font-size: 18px;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
th,
td {
  padding: 6px 2px;
  text-align: left;
  border-bottom: 1px solid #f2f3f5;
}
th {
  color: #86909c;
  font-weight: normal;
}
</style>
