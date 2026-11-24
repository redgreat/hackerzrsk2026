<script setup lang="ts">
import { api } from '@/api'
import type { RecordingDetail } from '@/types'
import { showFailToast } from 'vant'
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const recording = ref<RecordingDetail>()
const audioError = ref(false)
let countedPlay = false

watch(() => String(route.params.id), async (id, _, onCleanup) => {
  let current = true
  onCleanup(() => { current = false })
  recording.value = undefined
  audioError.value = false
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
</style>
