<script setup lang="ts">
import { api } from '@/api'
import { ApiError } from '@/api/http'
import LineTrend from '@/components/LineTrend.vue'
import ScoreRadar from '@/components/ScoreRadar.vue'
import type { Message, Report } from '@/types'
import { OUTCOME_LABEL, OUTCOME_TAG, scoreColor } from '@/utils/labels'
import { closeToast, showFailToast, showLoadingToast } from 'vant'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const sid = route.params.id as string

const report = ref<Report | null>(null)
const messages = ref<Message[]>([])
const waiting = ref(false)
const showTranscript = ref(false)
let timer: number | undefined
let tries = 0

const userSaid = computed(() => new Map(messages.value.filter((m) => m.role === 'user').map((m) => [m.turn, m.content])))
const trustLabels = computed(() => report.value?.trust_curve.map((_, i) => (i === 0 ? '开场' : `第${i}轮`)) ?? [])

async function load() {
  try {
    report.value = await api.report(sid)
    waiting.value = false
    messages.value = (await api.session(sid)).messages
  } catch (e) {
    if (e instanceof ApiError && e.status === 404 && tries++ < 30) {
      waiting.value = true
      timer = window.setTimeout(load, 2000)
    } else {
      waiting.value = false
      showFailToast((e as Error).message)
    }
  }
}

onMounted(load)
onBeforeUnmount(() => window.clearTimeout(timer))

async function again() {
  if (!report.value) return
  showLoadingToast({ message: '客户正在接通…', duration: 0, forbidClick: true })
  try {
    const s = await api.startSession(report.value.scenario_id)
    closeToast()
    router.replace(`/practice/${s.id}`)
  } catch (e) {
    showFailToast((e as Error).message)
  }
}
</script>

<template>
  <div class="page">
    <van-nav-bar title="评分报告" left-arrow @click-left="router.push('/history')" />

    <van-loading v-if="waiting" vertical class="wait">AI 教练正在评分，请稍候…</van-loading>

    <template v-if="report">
      <div class="card hero">
        <div class="score" :style="{ color: scoreColor(report.total_score) }">
          {{ report.total_score }}<small>分</small>
        </div>
        <div class="hero-meta">
          <van-tag :type="OUTCOME_TAG[report.outcome]" size="medium">{{ OUTCOME_LABEL[report.outcome] }}</van-tag>
          <span class="muted">{{ report.scenario_name }} · {{ report.turns }} 轮 · 求助 {{ report.hints_used }} 次</span>
        </div>
        <p class="summary">{{ report.summary }}</p>
      </div>

      <div class="card">
        <h3>能力雷达</h3>
        <ScoreRadar :dimensions="report.dimension_scores" />
        <div v-for="d in report.dimension_scores" :key="d.name" class="dim">
          <div class="dim-head">
            <span>{{ d.name }}</span>
            <van-rate :model-value="d.score" readonly size="13" color="#ff7d00" void-color="#e5e6eb" />
          </div>
          <div class="muted">{{ d.comment }}</div>
        </div>
      </div>

      <div class="card">
        <h3>亮点</h3>
        <div v-for="h in report.highlights" :key="h" class="point good"><van-icon name="success" /> {{ h }}</div>
        <h3 style="margin-top: 14px">改进建议</h3>
        <div v-for="i in report.improvements" :key="i" class="point warn"><van-icon name="info-o" /> {{ i }}</div>
      </div>

      <div v-if="report.turn_reviews.length" class="card">
        <h3>逐轮点评 · 推荐话术</h3>
        <div v-for="r in report.turn_reviews" :key="r.turn" class="review">
          <div class="muted">第 {{ r.turn }} 轮 · 你说</div>
          <div class="said">“{{ r.user_said }}”</div>
          <div class="issue"><b>问题：</b>{{ r.issue }}</div>
          <div class="better"><b>可以这样说：</b>{{ r.better_reply }}</div>
        </div>
      </div>

      <div class="card">
        <h3>客户信任值变化</h3>
        <LineTrend :values="report.trust_curve" :labels="trustLabels" />
      </div>

      <div v-if="report.inner_thoughts.length" class="card">
        <h3>客户内心独白复盘</h3>
        <van-steps direction="vertical" :active="report.inner_thoughts.length - 1" active-color="#1f6feb">
          <van-step v-for="t in report.inner_thoughts" :key="t.turn">
            <div class="thought-head">
              第 {{ t.turn }} 轮 · 信任 {{ t.trust_before }} → {{ t.trust_after }}
              <span :class="t.delta >= 0 ? 'up' : 'down'">{{ t.delta >= 0 ? '+' : '' }}{{ t.delta }}</span>
            </div>
            <div v-if="userSaid.get(t.turn)" class="muted">你：{{ userSaid.get(t.turn) }}</div>
            <div class="thought"><van-icon name="chat-o" /> {{ t.thought }}</div>
            <div class="tags">
              <van-tag v-for="b in t.behaviors" :key="b" plain>{{ b }}</van-tag>
              <van-tag v-if="t.resolved.length" type="success">化解顾虑 {{ t.resolved.length }} 个</van-tag>
            </div>
          </van-step>
        </van-steps>
      </div>

      <div class="card">
        <van-cell title="查看完整对话" is-link :arrow-direction="showTranscript ? 'up' : 'down'" @click="showTranscript = !showTranscript" />
        <div v-if="showTranscript" class="transcript">
          <div v-for="m in messages" :key="m.seq" :class="['line', m.role]">
            <b>{{ m.role === 'user' ? '我' : m.role === 'hint' ? '教练' : '客户' }}：</b>{{ m.content }}
          </div>
        </div>
      </div>

      <p v-if="report.references.length" class="muted refs">参考话术：{{ report.references.join('；') }}</p>

      <div class="bottom">
        <van-button type="primary" round block @click="again">再练一次</van-button>
        <van-button round block style="margin-top: 10px" @click="router.push('/')">换个场景</van-button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.wait {
  margin-top: 30vh;
}
.hero {
  text-align: center;
}
.score {
  font-size: 56px;
  font-weight: 700;
  line-height: 1.1;
}
.score small {
  font-size: 18px;
  margin-left: 2px;
}
.hero-meta {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
}
.summary {
  margin: 12px 0 0;
  font-size: 15px;
  line-height: 1.6;
}
.dim {
  padding: 8px 0;
  border-top: 1px solid #f2f3f5;
}
.dim-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
  font-size: 14px;
}
.point {
  margin: 6px 0;
  font-size: 14px;
  line-height: 1.6;
}
.good {
  color: #00a028;
}
.warn {
  color: #d25f00;
}
.review {
  padding: 10px 0;
  border-top: 1px solid #f2f3f5;
  font-size: 14px;
  line-height: 1.6;
}
.said {
  color: #4e5969;
}
.issue {
  color: #f53f3f;
}
.better {
  margin-top: 4px;
  padding: 8px 10px;
  background: #e8ffea;
  border-radius: 8px;
  color: #00742a;
}
.thought-head {
  font-weight: 600;
  color: #1f2329;
}
.up {
  color: #00b42a;
}
.down {
  color: #f53f3f;
}
.thought {
  margin: 4px 0;
  color: #4e5969;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.transcript {
  padding: 8px 4px 0;
  font-size: 14px;
  line-height: 1.7;
}
.line.hint {
  color: #d25f00;
}
.refs {
  margin: 0 16px;
}
.bottom {
  padding: 8px 16px 24px;
}
</style>
