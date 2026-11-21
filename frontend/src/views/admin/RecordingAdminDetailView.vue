<script setup lang="ts">
import { api } from '@/api'
import type { ChoiceQuestion, RecordingDetail } from '@/types'
import { formatDuration, QUESTION_TYPE, RECORDING_STATUS } from '@/utils/labels'
import { ElMessage } from 'element-plus'
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const rid = Number(route.params.id)
const d = ref<RecordingDetail | null>(null)
let timer: number | undefined

async function load() {
  d.value = await api.admin.recording(rid)
}
onMounted(async () => {
  await load()
  timer = window.setInterval(async () => {
    if (d.value && (d.value.status === 'transcribing' || d.value.status === 'analyzing')) await load()
  }, 3000)
})
onBeforeUnmount(() => window.clearInterval(timer))

async function process(force = false) {
  await api.admin.processRecording(rid, force)
  ElMessage.info('已开始处理')
  load()
}

async function togglePublish(v: string | number | boolean) {
  const pub = Boolean(v)
  try {
    await api.admin.updateRecording(rid, { published: pub })
    ElMessage.success(pub ? '已发布' : '已取消发布')
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
  load()
}

async function reviewQuestion(q: ChoiceQuestion, status: 'approved' | 'rejected') {
  await api.admin.updateQuestion(q.id, { status })
  load()
}
</script>

<template>
  <div v-if="d">
    <el-page-header style="margin-bottom: 12px" @back="router.push('/admin/recordings')">
      <template #content>录音 #{{ d.id }} {{ d.title }}</template>
    </el-page-header>

    <el-descriptions :column="3" border size="small">
      <el-descriptions-item label="状态">
        <el-tag :type="RECORDING_STATUS[d.status]?.type">{{ RECORDING_STATUS[d.status]?.label }}</el-tag>
        <span v-if="d.error" style="color: var(--el-color-danger); margin-left: 8px">{{ d.error }}</span>
      </el-descriptions-item>
      <el-descriptions-item label="客户类型">{{ d.customer_type || '—' }}</el-descriptions-item>
      <el-descriptions-item label="结果">{{ d.analysis?.outcome || '—' }}</el-descriptions-item>
      <el-descriptions-item label="时长">{{ formatDuration(d.duration_seconds) }}</el-descriptions-item>
      <el-descriptions-item label="播放次数">{{ d.play_count }}</el-descriptions-item>
      <el-descriptions-item label="来源">{{ d.source_key }}</el-descriptions-item>
      <el-descriptions-item label="发布">
        <el-switch :model-value="d.published" :disabled="d.status !== 'ready'" @change="togglePublish" />
        <span v-if="d.status !== 'ready'" style="margin-left: 8px; color: #909399">处理完成后才可发布</span>
      </el-descriptions-item>
      <el-descriptions-item label="操作" :span="2">
        <el-button size="small" type="primary" :disabled="d.status === 'transcribing' || d.status === 'analyzing'" @click="process(true)">转写 + 分析</el-button>
      </el-descriptions-item>
    </el-descriptions>

    <audio v-if="d.audio_url" :src="d.audio_url" controls style="width: 100%; margin: 12px 0" />

    <el-row :gutter="16">
      <el-col :span="12">
        <h3>转写文本（已脱敏）</h3>
        <div class="transcript">
          <div v-for="(t, i) in d.transcript" :key="i" class="line" :class="t.speaker">
            <b>{{ i }} {{ t.speaker === 'agent' ? '坐席' : '客户' }}</b> {{ t.text }}
          </div>
          <el-empty v-if="!d.transcript.length" description="尚未转写" :image-size="60" />
        </div>
      </el-col>
      <el-col :span="12">
        <template v-if="d.analysis">
          <h3>AI 分析</h3>
          <p>{{ d.analysis.summary }}</p>
          <p><el-tag v-for="t in d.tags" :key="t" size="small" style="margin-right: 4px">{{ t }}</el-tag></p>
          <h4>亮点话术</h4>
          <div v-for="h in d.analysis.highlights" :key="h.index" class="hl">
            <el-tag size="small" type="success">{{ h.technique }}</el-tag>
            「{{ d.transcript[h.index]?.text }}」<span class="muted">— {{ h.why }}</span>
          </div>
          <h4>新人学习要点</h4>
          <div v-for="p in d.analysis.learning_points" :key="p">· {{ p }}</div>
          <h4>合规问题</h4>
          <div v-for="i in d.analysis.compliance_issues" :key="i" style="color: var(--el-color-danger)">· {{ i }}</div>
          <div v-if="!d.analysis.compliance_issues.length" class="muted">无</div>
        </template>

        <h3 style="margin-top: 16px">AI 生成题目（审核后员工可见）</h3>
        <div v-for="q in d.questions" :key="q.id" class="q">
          <div>
            <el-tag size="small">{{ QUESTION_TYPE[q.type] }}</el-tag> {{ q.stem }}
            <el-tag :type="q.status === 'approved' ? 'success' : q.status === 'rejected' ? 'danger' : 'warning'" size="small" style="margin-left: 6px">
              {{ { pending: '待审核', approved: '已通过', rejected: '已驳回' }[q.status ?? 'pending'] }}
            </el-tag>
          </div>
          <div class="opts">
            <span v-for="(o, i) in q.options" :key="i" :class="{ ans: q.answer?.includes(i) }">{{ o }}</span>
          </div>
          <div class="muted">{{ q.explanation }}</div>
          <el-button v-if="q.status !== 'approved'" size="small" type="success" @click="reviewQuestion(q, 'approved')">通过</el-button>
          <el-button v-if="q.status !== 'rejected'" size="small" type="danger" plain @click="reviewQuestion(q, 'rejected')">驳回</el-button>
        </div>
        <el-empty v-if="!d.questions.length" description="暂无题目" :image-size="60" />
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.transcript {
  max-height: 70vh;
  overflow: auto;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 8px;
}
.line {
  padding: 4px 6px;
  border-bottom: 1px solid #f5f7fa;
  font-size: 13px;
}
.line b {
  color: #409eff;
  margin-right: 6px;
}
.line.customer b {
  color: #e6a23c;
}
.hl {
  padding: 4px 0;
  font-size: 13px;
}
.muted {
  color: #909399;
}
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
</style>
