<script setup lang="ts">
import { api } from '@/api'
import type { AdminAttempt } from '@/types'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import ExamQuestionBank from './ExamQuestionBank.vue'

const router = useRouter()
const items = ref<AdminAttempt[]>([])
const total = ref(0)
const page = ref(1)
const paperId = ref('')
const papers = ref<Awaited<ReturnType<typeof api.admin.papers>>>([])
const loading = ref(false)
const canClear = ref(false)
const clearing = ref(false)
const tab = ref('bank')
async function load() {
  loading.value = true
  try {
    const r = await api.admin.attempts({ paper_id: paperId.value, page: page.value, size: 20 })
    items.value = r.items
    total.value = r.total
    canClear.value = r.can_clear
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function clearRecords() {
  try {
    await ElMessageBox.confirm(
      '将删除所有考试和自测答卷及关联对练，保留题库与普通练习。此操作仅用于测试，无法撤销。',
      '清空考试记录',
      { type: 'warning', confirmButtonText: '确认清空' },
    )
  } catch {
    return
  }
  clearing.value = true
  try {
    const result = await api.admin.clearExamRecords()
    ElMessage.success(`已清空 ${result.attempts} 份答卷和 ${result.sessions} 场考试对练`)
    page.value = 1
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    clearing.value = false
  }
}

onMounted(async () => {
  try {
    papers.value = await api.admin.papers()
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
})
</script>

<template>
  <el-tabs v-model="tab">
    <el-tab-pane label="考试题库" name="bank">
      <ExamQuestionBank />
    </el-tab-pane>
    <el-tab-pane label="考试成绩" name="results" lazy>
      <p class="muted">可按试卷筛选，点「详情」核对考试结果和作答内容。</p>
      <div style="margin-bottom: 12px; display: flex; gap: 8px">
        <el-select v-model="paperId" placeholder="全部试卷" clearable style="width: 220px" @change="page = 1; load()">
          <el-option v-for="p in papers" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
        <el-button type="primary" @click="page = 1; load()">刷新</el-button>
        <el-button v-if="canClear" type="danger" plain :loading="clearing" :disabled="loading" @click="clearRecords">清空考试记录（测试）</el-button>
      </div>

      <el-table :data="items" v-loading="loading" border>
        <el-table-column prop="user.name" label="姓名" width="100" />
        <el-table-column prop="user.userid" label="工号" width="110" />
        <el-table-column prop="paper_name" label="试卷" min-width="160" />
        <el-table-column label="类型" width="90">
          <template #default="{ row }"><el-tag :type="row.kind === 'exam' ? 'danger' : 'primary'" size="small">{{ row.kind === 'exam' ? '考试' : '自测' }}</el-tag></template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><el-tag :type="row.status === 'submitted' ? 'info' : 'warning'" size="small">{{ row.status === 'submitted' ? '已交卷' : '进行中' }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="score" label="分数" width="80">
          <template #default="{ row }">{{ row.score ?? '—' }}</template>
        </el-table-column>
        <el-table-column label="结果" width="80">
          <template #default="{ row }">
            <el-tag v-if="row.passed === true" type="success" size="small">通过</el-tag>
            <el-tag v-else-if="row.passed === false" type="danger" size="small">未过</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="started_at" label="开始时间" width="160">
          <template #default="{ row }">{{ row.started_at?.slice(5, 16).replace('T', ' ') }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ row }"><el-button size="small" @click="router.push(`/admin/exams/${row.id}`)">详情</el-button></template>
        </el-table-column>
      </el-table>

      <el-pagination v-model:current-page="page" :total="total" :page-size="20" layout="total, prev, pager, next" style="margin-top: 12px" @change="load" />
    </el-tab-pane>
  </el-tabs>
</template>
