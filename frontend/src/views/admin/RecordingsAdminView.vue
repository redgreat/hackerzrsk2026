<script setup lang="ts">
import { api } from '@/api'
import type { RecordingCard, RecordingStatus } from '@/types'
import { formatDuration, RECORDING_STATUS } from '@/utils/labels'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const items = ref<(RecordingCard & { pending_questions: number })[]>([])
const statusCounts = ref<Record<string, number>>({})
const total = ref(0)
const page = ref(1)
const status = ref('')
const published = ref<boolean | ''>('')
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const r = await api.admin.recordings({ status: status.value, published: published.value === '' ? null : published.value ? 'true' : 'false', page: page.value, size: 20 })
    items.value = r.items
    total.value = r.total
    statusCounts.value = r.status_counts
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function add() {
  const { value: url } = await ElMessageBox.prompt('粘贴录音地址（OSS / 呼叫中心 URL）', '添加录音', {
    inputPattern: /^https?:\/\/.+/,
    inputErrorMessage: '请输入合法的 http(s) 地址',
  })
  await api.admin.addRecording(url.trim(), '')
  ElMessage.success('已添加，请在详情页执行转写分析')
  load()
}

async function process(r: RecordingCard, force = false) {
  await api.admin.processRecording(r.id, force)
  ElMessage.info('处理中，稍后刷新查看进度')
}

const st = (s: RecordingStatus) => RECORDING_STATUS[s] ?? { label: s, type: 'info' as const }
const busy = (s: RecordingStatus) => s === 'transcribing' || s === 'analyzing'
</script>

<template>
  <div style="margin-bottom: 12px; display: flex; gap: 8px; align-items: center">
    <el-select v-model="status" placeholder="全部状态" clearable style="width: 140px" @change="page = 1; load()">
      <el-option v-for="(v, k) in RECORDING_STATUS" :key="k" :label="`${v.label}（${statusCounts[k] ?? 0}）`" :value="k" />
    </el-select>
    <el-select v-model="published" placeholder="发布状态" clearable style="width: 130px" @change="page = 1; load()">
      <el-option label="已发布" :value="true" />
      <el-option label="未发布" :value="false" />
    </el-select>
    <el-button type="primary" @click="page = 1; load()">刷新</el-button>
    <el-button @click="add">添加录音</el-button>
  </div>

  <el-table :data="items" v-loading="loading" border>
    <el-table-column prop="id" label="ID" width="70" />
    <el-table-column prop="title" label="标题" min-width="180" />
    <el-table-column prop="customer_type" label="客户类型" width="110" />
    <el-table-column label="时长" width="80">
      <template #default="{ row }">{{ formatDuration(row.duration_seconds) }}</template>
    </el-table-column>
    <el-table-column label="状态" width="100">
      <template #default="{ row }">
        <el-tag :type="st(row.status).type">{{ st(row.status).label }}</el-tag>
        <el-tooltip v-if="row.error" :content="row.error"><el-icon style="margin-left: 4px"><Warning /></el-icon></el-tooltip>
      </template>
    </el-table-column>
    <el-table-column label="题目" width="90">
      <template #default="{ row }"><el-tag v-if="row.pending_questions" type="warning">待审 {{ row.pending_questions }}</el-tag></template>
    </el-table-column>
    <el-table-column label="发布" width="70">
      <template #default="{ row }"><el-tag v-if="row.published" type="success">已发布</el-tag></template>
    </el-table-column>
    <el-table-column prop="play_count" label="播放" width="70" />
    <el-table-column label="操作" width="260">
      <template #default="{ row }">
        <el-button size="small" :disabled="busy(row.status)" @click="process(row as RecordingCard, true)">{{ row.status === 'imported' ? '转写分析' : '重新处理' }}</el-button>
        <el-button size="small" @click="router.push(`/admin/recordings/${row.id}`)">详情</el-button>
      </template>
    </el-table-column>
  </el-table>

  <el-pagination v-model:current-page="page" :total="total" :page-size="20" layout="total, prev, pager, next" style="margin-top: 12px" @change="load" />
</template>
