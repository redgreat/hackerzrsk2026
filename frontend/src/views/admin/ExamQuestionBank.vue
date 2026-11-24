<script setup lang="ts">
import { api } from '@/api'
import type { ExamBankQuestion } from '@/types'
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'

const sources = ref<{ id: string; name: string }[]>([])
const scenarioId = ref('')
const count = ref(6)
const items = ref<ExamBankQuestion[]>([])
const page = ref(1)
const total = ref(0)
const status = ref<ExamBankQuestion['status'] | ''>('')
const loading = ref(false)
const generating = ref(false)
const reviewing = ref<number>()
const statusNames = { pending: '待审核', approved: '可抽题', archived: '已归档' }

async function load(reset = false) {
  if (reset) page.value = 1
  loading.value = true
  try {
    const result = await api.admin.examQuestions({ status: status.value || undefined, page: page.value })
    items.value = result.items
    total.value = result.total
    if (page.value > 1 && !items.value.length) {
      page.value--
      await load()
    }
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function generate() {
  generating.value = true
  try {
    const result = await api.admin.generateExamQuestions(scenarioId.value, count.value)
    ElMessage.success(`新增 ${result.created} 道待审核题，跳过 ${result.duplicates} 道重复题`)
    status.value = 'pending'
    await load(true)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    generating.value = false
  }
}

async function review(id: number, next: 'approved' | 'archived') {
  reviewing.value = id
  try {
    await api.admin.reviewExamQuestion(id, next)
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    reviewing.value = undefined
  }
}

onMounted(async () => {
  void load()
  try {
    sources.value = await api.admin.examQuestionSources()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
})
</script>

<template>
  <div class="toolbar">
    <el-select v-model="scenarioId" aria-label="来源练习" placeholder="选择已发布的练习" filterable style="width: 290px">
      <el-option v-for="source in sources" :key="source.id" :label="source.name" :value="source.id" />
    </el-select>
    <div class="question-count">
      <label for="exam-generation-count">本次最多生成</label>
      <el-input-number id="exam-generation-count" v-model="count" aria-label="本次最多生成题数" :min="1" :max="8" />
      <span>道</span>
    </div>
    <el-button type="primary" :loading="generating" :disabled="!scenarioId || !count" @click="generate">AI 生成合规题</el-button>
    <el-select v-model="status" aria-label="审核状态" placeholder="全部状态" clearable style="width: 130px" @change="load(true)">
      <el-option v-for="(name, key) in statusNames" :key="key" :label="name" :value="key" />
    </el-select>
  </div>
  <p class="muted">考点不足或有重复时，实际生成题数可能更少。新题审核为可用后才能被抽到。</p>
  <p class="muted">E01 每次开考从题库随机抽 12 道可用合规题和 2 场录音对练。</p>
  <el-table :data="items" v-loading="loading" row-key="id" border empty-text="暂无题目">
    <el-table-column type="expand">
      <template #default="{ row }">
        <div class="review">
          <ol type="A"><li v-for="(option, i) in row.options" :key="i" :class="{ correct: row.answer.includes(i) }">{{ option }}</li></ol>
          <p><strong>解析</strong> {{ row.explanation }}</p>
        </div>
      </template>
    </el-table-column>
    <el-table-column prop="stem" label="题干" min-width="260" />
    <el-table-column prop="topic" label="考点" min-width="120" />
    <el-table-column prop="scenario_name" label="来源练习" min-width="130" />
    <el-table-column label="状态" width="95">
      <template #default="{ row }">{{ statusNames[row.status as ExamBankQuestion['status']] }}</template>
    </el-table-column>
    <el-table-column label="操作" width="155">
      <template #default="{ row }">
        <el-button v-if="row.status !== 'approved'" size="small" :disabled="reviewing !== undefined" @click="review(row.id, 'approved')">设为可用</el-button>
        <el-button v-if="row.status !== 'archived'" size="small" :disabled="reviewing !== undefined" @click="review(row.id, 'archived')">归档</el-button>
      </template>
    </el-table-column>
  </el-table>
  <el-pagination v-model:current-page="page" :total="total" :page-size="20" layout="total, prev, pager, next" @current-change="load()" />
</template>

<style scoped>
.toolbar { display: flex; flex-wrap: wrap; gap: 8px; }
.question-count { display: flex; align-items: center; gap: 6px; white-space: nowrap; }
.question-count :deep(.el-input-number) { width: 112px; }
.review { padding: 4px 24px; }
.correct { color: #237346; font-weight: 600; }
</style>
