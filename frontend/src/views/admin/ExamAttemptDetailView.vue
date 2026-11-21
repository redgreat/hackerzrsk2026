<script setup lang="ts">
import { api } from '@/api'
import type { AttemptDetail, QuizItem, RoleplayItem } from '@/types'
import { QUESTION_TYPE } from '@/utils/labels'
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const d = ref<AttemptDetail | null>(null)
onMounted(async () => {
  d.value = await api.admin.attempt(route.params.id as string)
})
const quizItems = (s: AttemptDetail['sections'][number]) => s.items as QuizItem[]
const rpItems = (s: AttemptDetail['sections'][number]) => s.items as RoleplayItem[]
</script>

<template>
  <div v-if="d">
    <el-page-header style="margin-bottom: 12px" @back="router.push('/admin/exams')">
      <template #content>{{ d.paper_name }} · {{ d.user?.name }}（{{ d.user?.userid }}）</template>
    </el-page-header>

    <el-descriptions :column="4" border size="small" style="margin-bottom: 16px">
      <el-descriptions-item label="类型">{{ d.kind === 'exam' ? '正式考试' : '自测' }}</el-descriptions-item>
      <el-descriptions-item label="状态">{{ d.status === 'submitted' ? '已交卷' : '进行中' }}</el-descriptions-item>
      <el-descriptions-item label="总分">{{ d.score ?? '—' }}</el-descriptions-item>
      <el-descriptions-item label="结果">
        <el-tag v-if="d.passed === true" type="success">通过</el-tag>
        <el-tag v-else-if="d.passed === false" type="danger">未通过</el-tag>
      </el-descriptions-item>
    </el-descriptions>

    <div v-if="d.result" style="margin-bottom: 16px">
      <el-tag v-for="s in d.result.sections" :key="s.title" style="margin-right: 8px">{{ s.title }}：{{ s.score }} 分（权重 {{ s.weight }}）</el-tag>
    </div>

    <template v-for="sec in d.sections" :key="sec.title">
      <h3>{{ sec.title }}</h3>
      <template v-if="sec.type !== 'roleplay'">
        <div v-for="it in quizItems(sec)" :key="it.key" class="q">
          <div><el-tag size="small">{{ QUESTION_TYPE[it.type] }}</el-tag> {{ it.stem }}</div>
          <div class="opts">
            <span v-for="(o, i) in it.options" :key="i" :class="{ chosen: it.chosen.includes(i), ans: it.answer?.includes(i) }">{{ o }}</span>
          </div>
          <div class="muted">{{ it.explanation }}</div>
        </div>
      </template>
      <template v-else>
        <div v-for="it in rpItems(sec)" :key="it.key" class="q">
          {{ it.scenario_name }}：
          <template v-if="it.report_ready">得分 {{ it.score }}</template>
          <template v-else-if="it.session_id">进行中</template>
          <template v-else>未开始</template>
          <el-button v-if="it.session_id" size="small" link type="primary" @click="router.push(`/admin/sessions/${it.session_id}`)">看对练详情</el-button>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.q {
  padding: 8px;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  margin-bottom: 8px;
  font-size: 13px;
}
.opts span {
  margin-right: 10px;
  color: #606266;
}
.opts .ans {
  color: #67c23a;
  font-weight: 600;
}
.opts .chosen:not(.ans) {
  color: #f56c6c;
  text-decoration: line-through;
}
.muted {
  color: #909399;
}
</style>
