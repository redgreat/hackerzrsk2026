<script setup lang="ts">
import { api } from '@/api'
import type { AttemptSummary } from '@/types'
import { formatTime, scoreColor } from '@/utils/labels'
import { onMounted, ref } from 'vue'

const attempts = ref<AttemptSummary[]>([])
const loading = ref(false)
const loadError = ref('')
const hasMore = ref(false)
const pageSize = 30

async function load() {
  if (loading.value) return
  loading.value = true
  loadError.value = ''
  try {
    const page = await api.myAttempts(attempts.value.length, pageSize + 1)
    attempts.value.push(...page.slice(0, pageSize))
    hasMore.value = page.length > pageSize
  } catch (error) {
    loadError.value = (error as Error).message
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <van-nav-bar title="考试记录" left-arrow @click-left="$router.push('/my')" />
    <p class="page-guide">按开考时间从近到远显示。点开已交卷的记录可查看分项得分和答卷。</p>
    <van-skeleton v-if="loading && !attempts.length" :row="5" style="margin: 16px" />
    <van-cell-group v-if="attempts.length" inset>
      <van-cell
        v-for="attempt in attempts"
        :key="attempt.id"
        :title="attempt.paper_name || attempt.paper_id"
        :to="{ name: 'attempt', params: { id: attempt.id }, query: { from: 'history' } }"
        is-link
      >
        <template #label>{{ formatTime(attempt.submitted_at || attempt.started_at) }} · {{ attempt.status === 'submitted' ? '已交卷' : '开始考试' }}</template>
        <template #value>
          <template v-if="attempt.status === 'submitted'">
            <b v-if="attempt.score !== null" :style="{ color: scoreColor(attempt.score) }">{{ attempt.score }} 分</b>
            <van-tag v-if="attempt.passed !== null" :type="attempt.passed ? 'success' : 'danger'">{{ attempt.passed ? '通过' : '未通过' }}</van-tag>
          </template>
          <van-tag v-else type="primary">继续作答</van-tag>
        </template>
      </van-cell>
    </van-cell-group>
    <van-empty v-if="!loading && !attempts.length && !loadError" description="还没有考试记录">
      <van-button type="primary" round to="/exams">去考试</van-button>
    </van-empty>
    <div v-if="hasMore || loadError" class="more">
      <p v-if="loadError" class="muted" role="status">{{ loadError }}</p>
      <van-button plain size="small" :loading="loading" @click="load">{{ loadError ? '重试' : '加载更多' }}</van-button>
    </div>
  </div>
</template>

<style scoped>
b { display: block; font-size: 17px; margin-bottom: 2px; }
.more { margin: 18px 16px; text-align: center; }
</style>
