<script setup lang="ts">
import { api } from '@/api'
import type { RecordingDetail } from '@/types'
import { showFailToast } from 'vant'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const recording = ref<RecordingDetail>()
const audioError = ref(false)
const keyword = ref('')
const transcriptPanel = ref<HTMLElement>()
const activeMatch = ref(0)
const transcript = computed(() => recording.value?.learning_transcript ?? [])
const pattern = computed(() => {
  const query = keyword.value.trim()
  return query ? new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'i') : undefined
})
const lines = computed(() => transcript.value.map((line) => ({
  ...line,
  parts: pattern.value ? line.text.split(pattern.value) : [line.text],
})))
const matches = computed(() => lines.value.filter((line) => line.parts.length > 1))
let countedPlay = false

watch([keyword, activeMatch], () => {
  const match = matches.value[activeMatch.value]
  const row = match && transcriptPanel.value?.querySelector<HTMLElement>(`[data-seq="${match.seq}"]`)
  if (row) transcriptPanel.value?.scrollTo({ top: row.offsetTop })
}, { flush: 'post' })

watch(keyword, () => { activeMatch.value = 0 })

watch(() => String(route.params.id), async (id, _, onCleanup) => {
  let current = true
  onCleanup(() => { current = false })
  recording.value = undefined
  audioError.value = false
  keyword.value = ''
  countedPlay = false
  try {
    const detail = await api.recording(id)
    if (current) recording.value = detail
  } catch (error) {
    if (current) showFailToast((error as Error).message)
  }
}, { immediate: true })

function markPlayed() {
  if (!recording.value || countedPlay) return
  countedPlay = true
  void api.recordingPlayed(recording.value.id).catch(() => {})
}
</script>

<template>
  <div class="page">
    <van-nav-bar title="录音详情" left-arrow @click-left="router.push('/recordings')" />
    <template v-if="recording">
      <div class="learning-layout">
        <section class="card">
          <h2>{{ recording.title }}</h2>
          <audio :src="recording.audio_url" controls preload="metadata" @play="markPlayed" @error="audioError = true" />
          <p v-if="audioError" role="status" class="muted">暂时无法播放这条录音，请联系管理员核对地址。</p>
          <template v-if="recording.learning_note || recording.analysis?.learning_points.length">
            <h3>学习提示</h3>
            <p v-if="recording.learning_note" class="note">{{ recording.learning_note }}</p>
            <ul v-else>
              <li v-for="point in recording.analysis?.learning_points" :key="point">{{ point }}</li>
            </ul>
          </template>
        </section>
        <section class="card transcript-card" aria-labelledby="transcript-title">
          <h3 id="transcript-title">录音转写</h3>
          <template v-if="transcript.length">
            <div class="transcript-search">
              <input v-model="keyword" type="search" aria-label="搜索转写关键词" placeholder="搜索关键词" />
              <template v-if="matches.length > 1">
                <button type="button" @click="activeMatch = (activeMatch + matches.length - 1) % matches.length">上一处</button>
                <button type="button" @click="activeMatch = (activeMatch + 1) % matches.length">下一处</button>
              </template>
            </div>
            <p v-if="pattern" class="muted search-status" role="status">
              {{ matches.length ? `第 ${activeMatch + 1} / ${matches.length} 段` : '未找到匹配的文字' }}
            </p>
            <div ref="transcriptPanel" class="transcript-scroll" tabindex="0" role="region" aria-label="转写全文">
              <p v-for="line in lines" :key="line.seq" :data-seq="line.seq" class="transcript-line"
                :class="{ 'active-match': matches[activeMatch]?.seq === line.seq }">
                <span class="speaker">{{ line.speaker }}</span>
                <template v-for="(part, i) in line.parts" :key="i">
                  <mark v-if="i % 2">{{ part }}</mark><template v-else>{{ part }}</template>
                </template>
              </p>
            </div>
          </template>
          <p v-else class="muted">这条录音暂无可用转写。</p>
        </section>
      </div>
      <section class="card">
        <h3>从本录音提取的练习</h3>
        <van-cell
          v-for="scenario in recording.extracted_scenarios"
          :key="scenario.id"
          :title="`${scenario.id} · ${scenario.name}`"
          :to="`/scenario/${scenario.id}`"
          is-link
        />
        <p v-if="!recording.extracted_scenarios.length" class="muted">这条录音暂未配置提取练习。</p>
      </section>
    </template>
  </div>
</template>

<style scoped>
h2 { margin: 0 0 12px; font-size: 18px; }
h3 { margin: 12px 0 8px; font-size: 16px; }
audio { display: block; width: 100%; }
.note { white-space: pre-wrap; }
.learning-layout { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 3fr); align-items: start; }
.transcript-card h3 { margin-top: 0; }
.transcript-search { display: flex; flex-wrap: wrap; gap: 6px; }
.transcript-search input, .transcript-search button {
  min-height: 36px;
  padding: 4px 8px;
  border: 1px solid #c9cdd4;
  border-radius: 6px;
  background: #fff;
  font: inherit;
}
.transcript-search input { flex: 1 1 120px; min-width: 0; }
.transcript-search button { color: #1f6feb; cursor: pointer; }
.search-status { margin: 6px 0 0; }
.transcript-scroll { position: relative; max-height: min(42vh, 360px); margin-top: 8px; overflow-y: auto; }
.transcript-line { margin: 0; padding: 8px; line-height: 1.6; white-space: pre-wrap; overflow-wrap: anywhere; }
.speaker { display: block; color: #4e5969; font-size: 12px; }
.active-match { background: #eef5ff; }
mark { background: #ffe59a; color: inherit; }
@media (max-width: 700px) {
  .learning-layout { grid-template-columns: minmax(0, 1fr); }
}
</style>
