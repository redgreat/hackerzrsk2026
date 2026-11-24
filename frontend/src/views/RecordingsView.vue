<script setup lang="ts">
import { api } from '@/api'
import type { RecordingPage } from '@/types'
import { showFailToast } from 'vant'
import { onMounted, ref } from 'vue'

const items = ref<RecordingPage['items']>([])
const page = ref(1)
const total = ref(0)
const loading = ref(false)
const loaded = ref(false)

async function loadMore() {
  if (loading.value) return
  loading.value = true
  try {
    const result = await api.recordings({ page: page.value, size: 20 })
    items.value.push(...result.items)
    total.value = result.total
    page.value += 1
    loaded.value = true
  } catch (error) {
    showFailToast((error as Error).message)
  } finally {
    loading.value = false
  }
}

onMounted(loadMore)
</script>

<template>
  <div class="page">
    <van-nav-bar title="录音学习" />
    <router-link
      v-for="recording in items"
      :key="recording.id"
      :to="`/recordings/${recording.id}`"
      class="card recording"
    >
      <div class="recording-title">
        <van-icon name="music-o" />
        <strong>{{ recording.title }}</strong>
        <van-icon name="arrow" />
      </div>
      <div v-if="recording.extracted_scenarios.length" class="scenarios">
        <van-tag v-for="scenario in recording.extracted_scenarios" :key="scenario.id" plain type="primary">
          {{ scenario.id }} · {{ scenario.name }}
        </van-tag>
      </div>
    </router-link>
    <van-empty v-if="loaded && !items.length" description="暂无已发布录音" />
    <div v-if="!loaded || items.length < total" class="card">
      <van-button plain block :loading="loading" @click="loadMore">{{ loaded ? '加载更多' : '加载录音' }}</van-button>
    </div>
  </div>
</template>

<style scoped>
.recording { display: block; color: inherit; }
.recording-title { display: flex; align-items: center; gap: 10px; }
.recording-title strong { flex: 1; }
.scenarios { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
</style>
