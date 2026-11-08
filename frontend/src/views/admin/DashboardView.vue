<script setup lang="ts">
import { api } from '@/api'
import { VChart } from '@/components/charts'
import type { Overview, TrendPoint } from '@/types'
import { PURPOSE_LABEL, pct } from '@/utils/labels'
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'

const overview = ref<Overview | null>(null)
const trend = ref<TrendPoint[]>([])
const days = ref(30)

async function load() {
  try {
    ;[overview.value, trend.value] = await Promise.all([api.admin.overview(), api.admin.trend(days.value)])
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}
onMounted(load)
watch(days, load)

const cards = computed(() => {
  const o = overview.value
  if (!o) return []
  return [
    { label: '完成练习', value: o.finished_sessions },
    { label: '参与员工', value: o.users },
    { label: '平均分', value: o.avg_score ?? '-' },
    { label: '成功推进率', value: pct(o.deal_rate) },
    { label: '平均单次成本', value: `¥${o.avg_cost_yuan.toFixed(3)}` },
    { label: '相比人工带教节省', value: pct(o.cost_saving_ratio) },
  ]
})

const option = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: ['练习次数', '平均分'] },
  grid: { left: 48, right: 48, top: 40, bottom: 30 },
  xAxis: { type: 'category', data: trend.value.map((t) => t.day.slice(5, 10)) },
  yAxis: [
    { type: 'value', name: '次数', minInterval: 1 },
    { type: 'value', name: '均分', min: 0, max: 100 },
  ],
  series: [
    { name: '练习次数', type: 'bar', data: trend.value.map((t) => t.sessions), itemStyle: { color: '#8fb8ff' } },
    { name: '平均分', type: 'line', yAxisIndex: 1, smooth: true, data: trend.value.map((t) => t.avg_score), itemStyle: { color: '#1f6feb' } },
  ],
}))
</script>

<template>
  <div>
    <el-row :gutter="16">
      <el-col v-for="c in cards" :key="c.label" :span="4">
        <el-card shadow="never" class="stat">
          <div class="label">{{ c.label }}</div>
          <div class="value">{{ c.value }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="block">
      <template #header>
        <div class="head">
          <span>练习趋势</span>
          <el-radio-group v-model="days" size="small">
            <el-radio-button :value="7">近 7 天</el-radio-button>
            <el-radio-button :value="30">近 30 天</el-radio-button>
            <el-radio-button :value="90">近 90 天</el-radio-button>
          </el-radio-group>
        </div>
      </template>
      <VChart :option="option" autoresize style="height: 300px" />
    </el-card>

    <el-row :gutter="16">
      <el-col :span="12">
        <el-card shadow="never" class="block">
          <template #header>分场景</template>
          <el-table :data="overview?.by_scenario ?? []" size="small">
            <el-table-column prop="scenario" label="场景" />
            <el-table-column prop="count" label="完成次数" width="100" />
            <el-table-column prop="avg_score" label="平均分" width="100" />
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never" class="block">
          <template #header>模型 / 语音调用明细</template>
          <el-table :data="overview?.by_purpose ?? []" size="small">
            <el-table-column label="用途" min-width="100">
              <template #default="{ row }">{{ PURPOSE_LABEL[row.purpose] ?? row.purpose }}</template>
            </el-table-column>
            <el-table-column prop="calls" label="次数" width="80" />
            <el-table-column label="Token（入/出）" min-width="150">
              <template #default="{ row }">{{ row.prompt_tokens }} / {{ row.completion_tokens }}</template>
            </el-table-column>
            <el-table-column label="费用（元）" width="110">
              <template #default="{ row }">{{ row.cost_yuan.toFixed(3) }}</template>
            </el-table-column>
            <el-table-column label="平均耗时" width="100">
              <template #default="{ row }">{{ row.avg_latency_ms }} ms</template>
            </el-table-column>
          </el-table>
          <p class="note">累计模型与语音费用 ¥{{ overview?.total_cost_yuan?.toFixed(2) ?? '-' }}</p>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.stat {
  text-align: center;
  margin-bottom: 16px;
}
.label {
  color: #86909c;
  font-size: 13px;
}
.value {
  margin-top: 6px;
  font-size: 24px;
  font-weight: 600;
  color: #1f6feb;
}
.block {
  margin-bottom: 16px;
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.note {
  color: #86909c;
  font-size: 12px;
  margin: 8px 0 0;
}
</style>
