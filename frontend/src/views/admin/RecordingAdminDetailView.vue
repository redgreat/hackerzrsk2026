<script setup lang="ts">
import { api } from '@/api'
import type { AdminScenario, RecordingDetail } from '@/types'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const router = useRouter()
const rid = Number(useRoute().params.id)
const detail = ref<RecordingDetail>()
const transcripts = ref<{ id: number; name: string }[]>([])
const scenarios = ref<AdminScenario[]>([])
const snapshotId = ref<number>()
const extractedIds = ref<string[]>([])
const note = ref('')
const first = ref<number>()
const last = ref<number>()
const working = ref(false)

onMounted(async () => {
  try {
    const [recording, sources, available] = await Promise.all([
      api.admin.recording(rid), api.admin.recordingTranscripts(), api.admin.scenarios(),
    ])
    detail.value = recording
    transcripts.value = sources
    scenarios.value = available
    snapshotId.value = recording.transcript_snapshot_id ?? undefined
    extractedIds.value = (recording.practice_candidates ?? [])
      .filter((item) => !item.yaml && item.status !== 'archived').map((item) => item.id)
    note.value = recording.learning_note
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
})

async function change(action: () => Promise<RecordingDetail>) {
  if (working.value) return
  working.value = true
  try {
    detail.value = await action()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    working.value = false
  }
}

async function generate(manual = false) {
  if (manual && (!first.value || !last.value)) return
  const start = manual ? first.value : undefined
  const end = manual ? last.value : undefined
  try {
    await ElMessageBox.confirm(
      manual ? '请确认所选片段已核对并完成去标识处理。' : '请确认这份转写允许用于 AI 训练素材处理。系统会先脱敏和筛选，再生成待审核的练习。',
      '生成练习',
    )
  } catch {
    return
  }
  await change(() => api.admin.generateRecordingPractices(rid, start, end))
}

async function togglePublish() {
  const published = !detail.value?.published
  try {
    await ElMessageBox.confirm(
      published ? '确认音频可以向员工展示。此次发布会同时公开所有未归档的练习。' : '撤销后员工无法开始或继续关联练习，仍可查看已有成绩。',
      published ? '发布录音与练习' : '撤销发布',
    )
  } catch {
    return
  }
  await change(() => api.admin.updateRecording(rid, { published }))
}

async function review(id: string, status: 'approved' | 'archived') {
  await change(() => api.admin.reviewRecordingPractice(rid, id, status))
  extractedIds.value = (detail.value?.practice_candidates ?? [])
    .filter((item) => !item.yaml && item.status !== 'archived').map((item) => item.id)
}

function downloadYaml(id: string, yaml: string) {
  const url = URL.createObjectURL(new Blob([yaml], { type: 'application/yaml' }))
  const link = document.createElement('a')
  link.href = url
  link.download = id + '.yaml'
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}
</script>

<template>
  <div v-if="detail" class="recording-admin">
    <el-page-header @back="router.push('/admin/recordings')">
      <template #content>{{ detail.title }}</template>
      <template #extra>
        <el-button :type="detail.published ? 'default' : 'primary'" :disabled="working" @click="togglePublish">
          {{ detail.published ? '撤销发布' : '发布录音与练习' }}
        </el-button>
      </template>
    </el-page-header>

    <el-card shadow="never">
      <template #header>录音和学习提示</template>
      <audio :src="detail.audio_url" controls preload="none" />
      <el-form label-position="top">
        <el-form-item label="员工端学习提示">
          <el-input v-model="note" type="textarea" :rows="3" maxlength="600" />
        </el-form-item>
        <el-form-item label="关联现有练习">
          <el-select v-model="extractedIds" multiple filterable :multiple-limit="20">
            <el-option
              v-for="scenario in scenarios"
              :key="scenario.id"
              :value="scenario.id"
              :label="scenario.id + ' · ' + scenario.name"
            />
            <el-option
              v-for="item in detail.practice_candidates?.filter((item) => !item.yaml && !scenarios.some((scene) => scene.id === item.id))"
              :key="item.id"
              :value="item.id"
              :label="item.id + ' · ' + item.name"
            />
          </el-select>
        </el-form-item>
        <el-button :disabled="working" @click="change(() => api.admin.updateRecording(rid, { learning_note: note, extracted_scenario_ids: extractedIds }))">保存学习内容</el-button>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <template #header>已有 AI 转写</template>
      <div class="actions">
        <el-select v-model="snapshotId" filterable placeholder="选择已导入的 AI 转写">
          <el-option v-for="source in transcripts" :key="source.id" :value="source.id" :label="source.name" />
        </el-select>
        <el-button :disabled="working || !snapshotId" @click="change(() => api.admin.updateRecording(rid, { transcript_snapshot_id: snapshotId }))">关联转写</el-button>
      </div>
      <div v-if="detail.source_transcript?.length" class="transcript">
        <p v-for="row in detail.source_transcript" :key="row.seq"><b>{{ row.seq }} · 声道 {{ row.channel }}</b> {{ row.text }}</p>
      </div>
      <el-empty v-else description="尚未关联转写" :image-size="55" />
      <div class="range">
        <el-button type="primary" :loading="working" :disabled="!detail.transcript_snapshot_id" @click="generate()">AI 生成练习</el-button>
        <details class="range">
          <summary>高级选项 · 指定片段</summary>
          <div class="actions range">
            <el-input-number v-model="first" :min="1" aria-label="开始片段编号" placeholder="起始编号" />
            <span>至</span>
            <el-input-number v-model="last" :min="1" aria-label="结束片段编号" placeholder="结束编号" />
            <el-button :loading="working" :disabled="!detail.transcript_snapshot_id || !first || !last" @click="generate(true)">按片段生成</el-button>
          </div>
        </details>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header>提取练习</template>
      <el-empty v-if="!detail.practice_candidates?.length" description="暂无提取练习" :image-size="55" />
      <div v-for="item in detail.practice_candidates" :key="item.id" class="candidate">
        <div class="actions">
          <strong>{{ item.id }} · {{ item.name }}</strong>
          <el-tag>{{ { pending: '待审核', approved: '可发布', archived: '已归档' }[item.status] }}</el-tag>
          <el-button v-if="item.status !== 'approved'" size="small" :disabled="working" @click="review(item.id, 'approved')">设为可用</el-button>
          <el-button v-if="item.status !== 'archived'" size="small" :disabled="working" @click="review(item.id, 'archived')">归档</el-button>
          <el-button v-if="item.yaml" size="small" @click="downloadYaml(item.id, item.yaml)">下载 YAML</el-button>
        </div>
        <p v-if="item.source_seqs?.length">生成素材来自转写 #{{ item.transcript_snapshot_id }} 的片段 {{ item.source_seqs.join('、') }}</p>
        <details v-if="item.yaml">
          <summary>查看 YAML</summary>
          <pre>{{ item.yaml }}</pre>
        </details>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.recording-admin { display: grid; gap: 16px; }
audio { display: block; width: 100%; margin-bottom: 16px; }
.actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.actions .el-select { width: min(420px, 100%); }
.range { margin-top: 12px; }
.transcript { max-height: 300px; overflow-y: auto; margin-top: 12px; }
.candidate + .candidate { border-top: 1px solid #e4e7ed; margin-top: 12px; padding-top: 12px; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #f5f7fa; padding: 12px; }
</style>
