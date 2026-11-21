<script setup lang="ts">
import { api } from '@/api'
import type { RecordingCard } from '@/types'
import { formatDuration } from '@/utils/labels'
import { showFailToast } from 'vant'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const loading = ref(true)
const q = ref('')
const customerType = ref('')
const types = ref<{ name: string; count: number }[]>([])
const items = ref<RecordingCard[]>([])
const total = ref(0)
const page = ref(1)
const finished = ref(false)

async function load(reset = false) {
  if (reset) {
    items.value = []
    page.value = 1
    finished.value = false
  }
  try {
    const r = await api.recordings({ q: q.value.trim(), customer_type: customerType.value, page: page.value, size: 20 })
    types.value = r.customer_types
    total.value = r.total
    items.value.push(...r.items)
    if (items.value.length >= r.total) finished.value = true
    page.value += 1
  } catch (e) {
    showFailToast((e as Error).message)
  } finally {
    loading.value = false
  }
}

onMounted(() => load(true))
</script>

<template>
  <div class="page">
    <van-nav-bar title="优秀录音" />
    <van-search v-model="q" placeholder="搜索标题或标签" @search="load(true)" @clear="load(true)" />

    <van-dropdown-menu v-if="types.length">
      <van-dropdown-item
        v-model="customerType"
        :options="[{ text: '全部客户类型', value: '' }, ...types.map((t) => ({ text: `${t.name}（${t.count}）`, value: t.name }))]"
        @change="load(true)"
      />
    </van-dropdown-menu>

    <van-skeleton v-if="loading" :row="6" style="margin: 16px" />

    <van-list v-model:finished="finished" finished-text="没有更多了" @load="load()">
      <div v-for="r in items" :key="r.id" class="card rec" @click="router.push(`/recordings/${r.id}`)">
        <div class="head">
          <van-icon name="service-o" size="20" color="#1f6feb" />
          <div class="title">{{ r.title }}</div>
          <span class="muted">{{ formatDuration(r.duration_seconds) }}</span>
        </div>
        <p v-if="r.summary" class="summary">{{ r.summary }}</p>
        <div class="meta">
          <van-tag v-if="r.customer_type" plain type="primary">{{ r.customer_type }}</van-tag>
          <van-tag v-if="r.outcome" plain type="success">{{ r.outcome }}</van-tag>
          <van-tag v-for="t in r.tags" :key="t" plain>{{ t }}</van-tag>
          <span class="muted" style="margin-left: auto"><van-icon name="play" /> {{ r.play_count }}</span>
        </div>
      </div>
    </van-list>

    <van-empty v-if="!loading && !items.length" description="暂无已发布的优秀录音" />
  </div>
</template>

<style scoped>
.rec .head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.rec .title {
  flex: 1;
  font-size: 15px;
  font-weight: 600;
}
.summary {
  margin: 8px 0;
  font-size: 14px;
  color: #4e5969;
}
.meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}
</style>
