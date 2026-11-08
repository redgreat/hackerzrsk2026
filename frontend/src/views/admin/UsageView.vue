<script setup lang="ts">
import { api } from '@/api'
import { VChart } from '@/components/charts'
import type { UsagePage } from '@/types'
import { PURPOSE_LABEL, formatTime } from '@/utils/labels'
import { ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const loading = ref(false)
const data = ref<UsagePage | null>(null)
const filter = reactive({ purpose: undefined as string | undefined, page: 1, size: 50 })

async function load() {
  loading.value = true
  try {
    data.value = await api.admin.usage({ ...filter })
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

onMounted(load)

const option = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 48, right: 48, top: 30, bottom: 30 },
  legend: { data: ['费用（元）', 'Token（千）'] },
  xAxis: { type: 'category', data: (data.value?.daily ?? []).map((d) => d.day.slice(5, 10)) },
  yAxis: [{ type: 'value', name: '元' }, { type: 'value', name: '千 Token' }],
  series: [
    { name: '费用（元）', type: 'bar', data: (data.value?.daily ?? []).map((d) => d.cost_yuan), itemStyle: { color: '#ff7d00' } },
    { name: 'Token（千）', type: 'line', yAxisIndex: 1, smooth: true, data: (data.value?.daily ?? []).map((d) => +(d.tokens / 1000).toFixed(1)) },
  ],
}))

const purposes = Object.entries(PURPOSE_LABEL)
</script>

<template>
  <div>
    <el-card shadow="never" class="block">
      <template #header>近 30 天每日用量</template>
      <VChart :option="option" autoresize style="height: 260px" />
    </el-card>

    <el-card shadow="never">
      <el-form inline @submit.prevent>
        <el-form-item label="用途">
          <el-select v-model="filter.purpose" clearable placeholder="全部" style="width: 160px" @change="() => { filter.page = 1; load() }">
            <el-option v-for="[value, label] in purposes" :key="value" :label="label" :value="value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <span class="muted">共 {{ data?.total ?? 0 }} 条调用记录（不含对话内容）</span>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="data?.items ?? []" stripe size="small">
        <el-table-column label="时间" width="130">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="用途" width="100">
          <template #default="{ row }">{{ PURPOSE_LABEL[row.purpose] ?? row.purpose }}</template>
        </el-table-column>
        <el-table-column prop="model" label="模型" min-width="140" />
        <el-table-column prop="prompt_tokens" label="入 Token" width="100" />
        <el-table-column prop="completion_tokens" label="出 Token" width="100" />
        <el-table-column label="语音" width="110">
          <template #default="{ row }">
            {{ row.audio_seconds ? `${row.audio_seconds}s` : '' }}{{ row.tts_chars ? `${row.tts_chars} 字` : '' }}
          </template>
        </el-table-column>
        <el-table-column label="费用（元）" width="110">
          <template #default="{ row }">{{ row.cost_yuan.toFixed(4) }}</template>
        </el-table-column>
        <el-table-column prop="latency_ms" label="耗时 ms" width="100" />
        <el-table-column label="会话" min-width="110">
          <template #default="{ row }">
            <el-link v-if="row.session_id" type="primary" @click="router.push(`/admin/sessions/${row.session_id}`)">查看</el-link>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="filter.page"
        :page-size="filter.size"
        :total="data?.total ?? 0"
        layout="total, prev, pager, next"
        class="pager"
        @current-change="load"
      />
    </el-card>
  </div>
</template>

<style scoped>
.block {
  margin-bottom: 16px;
}
.muted {
  color: #86909c;
  font-size: 12px;
}
.pager {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
