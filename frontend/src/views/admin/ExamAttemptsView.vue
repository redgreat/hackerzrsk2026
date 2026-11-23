<script setup lang="ts">
import { api } from '@/api'
import type { AdminAttempt } from '@/types'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const items = ref<AdminAttempt[]>([])
const total = ref(0)
const page = ref(1)
const paperId = ref('')
const papers = ref<Awaited<ReturnType<typeof api.admin.papers>>>([])
const loading = ref(false)
const publishing = ref('')

async function publish(id: string) {
  try {
    await ElMessageBox.confirm('新开考的学员将使用本次发布的题目和评分规则。已开考的学员继续使用原版本。', '发布试卷')
  } catch {
    return
  }
  publishing.value = id
  try {
    await api.admin.publishPaper(id)
    papers.value = await api.admin.papers()
    ElMessage.success('试卷已发布')
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    publishing.value = ''
  }
}

async function load() {
  loading.value = true
  try {
    const r = await api.admin.attempts({ paper_id: paperId.value, page: page.value, size: 20 })
    items.value = r.items
    total.value = r.total
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
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
  <el-table :data="papers.filter((p) => p.kind === 'exam' && p.enabled)" border style="margin-bottom: 16px">
    <el-table-column prop="name" label="正式试卷" />
    <el-table-column label="发布状态">
      <template #default="{ row }">{{ row.publication_id ? `已发布 · 版本 ${row.publication_id}` : '待发布' }}</template>
    </el-table-column>
    <el-table-column label="操作">
      <template #default="{ row }">
        <el-button :loading="publishing === row.id" :disabled="!!publishing" @click="publish(row.id)">
          {{ row.publication_id ? '发布当前配置为新版本' : '发布试卷' }}
        </el-button>
      </template>
    </el-table-column>
  </el-table>
  <div style="margin-bottom: 12px; display: flex; gap: 8px">
    <el-select v-model="paperId" placeholder="全部试卷" clearable style="width: 220px" @change="page = 1; load()">
      <el-option v-for="p in papers" :key="p.id" :label="p.name" :value="p.id" />
    </el-select>
    <el-button type="primary" @click="page = 1; load()">刷新</el-button>
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
</template>
