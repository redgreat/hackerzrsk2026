<script setup lang="ts">
import { api } from '@/api'
import type { ChoiceQuestion, RecordingDetail } from '@/types'
import { formatDuration } from '@/utils/labels'
import { showFailToast } from 'vant'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const rid = Number(route.params.id)

const detail = ref<RecordingDetail | null>(null)
const audio = ref<HTMLAudioElement | null>(null)
const played = ref(false)
const tab = ref('learn')
// 答题状态：{题目id: 所选下标 / 判分结果}
const picked = ref<Record<number, number[]>>({})
const judged = ref<Record<number, { correct: boolean; answer: number[]; explanation: string }>>({})

const a = computed(() => detail.value?.analysis)

function seek(ms: number) {
  const el = audio.value
  if (el) {
    el.currentTime = ms / 1000
    el.play().catch(() => {})
  }
}

function onPlay() {
  if (!played.value) {
    played.value = true
    api.recordingPlayed(rid).catch(() => {})
  }
}

function choose(q: ChoiceQuestion, idx: number) {
  if (judged.value[q.id]) return
  const cur = picked.value[q.id] ?? []
  picked.value[q.id] = q.type === 'multi' ? (cur.includes(idx) ? cur.filter((i) => i !== idx) : [...cur, idx]) : [idx]
}

async function submit(q: ChoiceQuestion) {
  const ans = picked.value[q.id] ?? []
  if (!ans.length) return showFailToast('请先选择')
  try {
    judged.value[q.id] = await api.checkQuestion(rid, q.id, ans)
  } catch (e) {
    showFailToast((e as Error).message)
  }
}

function isMulti(q: ChoiceQuestion) {
  return q.type === 'multi'
}

onMounted(async () => {
  try {
    detail.value = await api.recording(rid)
  } catch (e) {
    showFailToast((e as Error).message)
  }
})
</script>

<template>
  <div class="page">
    <van-nav-bar :title="detail?.title || '录音学习'" left-arrow @click-left="router.back()" />

    <template v-if="detail">
      <div class="card">
        <audio ref="audio" :src="detail.audio_url" controls style="width: 100%" @play="onPlay" />
        <div class="meta">
          <van-tag v-if="detail.customer_type" plain type="primary">{{ detail.customer_type }}</van-tag>
          <van-tag v-if="a?.outcome" plain type="success">{{ a.outcome }}</van-tag>
          <van-tag v-for="t in detail.tags" :key="t" plain>{{ t }}</van-tag>
        </div>
        <p v-if="a?.summary" class="muted">{{ a.summary }}</p>
      </div>

      <van-tabs v-model:active="tab">
        <van-tab name="learn" title="点评学习" />
        <van-tab name="transcript" title="转写（点句跳转）" />
        <van-tab v-if="detail.questions.length" name="quiz" :title="`答题 ${detail.questions.length}`" />
      </van-tabs>

      <template v-if="tab === 'learn' && a">
        <div class="card">
          <h3>通话脉络（点击跳到对应位置）</h3>
          <van-steps direction="vertical" :active="a.stages.length - 1" active-color="#1f6feb">
            <van-step v-for="s in a.stages" :key="s.start_index">
              <div class="stage" @click="seek(detail.transcript[s.start_index]?.begin_ms ?? 0)">
                {{ s.name }}
                <span class="muted"> {{ detail.transcript[s.start_index]?.text.slice(0, 18) }}…</span>
              </div>
            </van-step>
          </van-steps>
        </div>

        <div class="card">
          <h3>亮点话术</h3>
          <div v-for="h in a.highlights" :key="h.index" class="hl" @click="seek(detail.transcript[h.index]?.begin_ms ?? 0)">
            <van-tag type="primary">{{ h.technique }}</van-tag>
            <div class="said">“{{ detail.transcript[h.index]?.text }}”</div>
            <div class="muted">{{ h.why }}</div>
          </div>
        </div>

        <div class="card">
          <h3>新人学习要点</h3>
          <div v-for="p in a.learning_points" :key="p" class="point"><van-icon name="success" color="#00b42a" /> {{ p }}</div>
        </div>

        <div v-if="a.compliance_issues.length" class="card">
          <h3>合规提醒</h3>
          <div v-for="i in a.compliance_issues" :key="i" class="point"><van-icon name="warning-o" color="#f53f3f" /> {{ i }}</div>
        </div>

        <div v-if="a.dimension_scores.length" class="card">
          <h3>质检评分（标杆参考）</h3>
          <div v-for="d in a.dimension_scores" :key="d.name" class="dim">
            <div class="dim-head">
              <span>{{ d.name }}</span>
              <van-rate :model-value="d.score" readonly size="13" color="#ff7d00" void-color="#e5e6eb" />
            </div>
            <div class="muted">{{ d.comment }}</div>
          </div>
        </div>

        <div v-if="detail.related_scenarios?.length" class="card">
          <h3>去练一遍</h3>
          <div v-for="s in detail.related_scenarios" :key="s.id" class="scenario" @click="router.push(`/scenario/${s.id}`)">
            <van-icon name="aim" color="#1f6feb" /> {{ s.name }} <van-icon name="arrow" color="#c9cdd4" />
          </div>
        </div>
      </template>

      <div v-if="tab === 'transcript'" class="card transcript">
        <div
          v-for="(t, i) in detail.transcript"
          :key="i"
          class="line"
          :class="t.speaker"
          @click="seek(t.begin_ms)"
        >
          <b>{{ t.speaker === 'agent' ? '坐席' : '客户' }}</b>
          <span class="time">{{ formatDuration(t.begin_ms / 1000) }}</span>
          {{ t.text }}
        </div>
      </div>

      <template v-if="tab === 'quiz'">
        <div v-for="q in detail.questions" :key="q.id" class="card">
          <h3>{{ q.stem }}</h3>
          <div
            v-for="(opt, i) in q.options"
            :key="i"
            class="opt"
            :class="{
              picked: (picked[q.id] ?? []).includes(i),
              right: judged[q.id]?.answer.includes(i),
              wrong: judged[q.id] && (picked[q.id] ?? []).includes(i) && !judged[q.id].answer.includes(i),
            }"
            @click="choose(q, i)"
          >
            <van-icon :name="judged[q.id]?.answer.includes(i) ? 'success' : isMulti(q) ? 'stop' : 'circle'" />
            {{ opt }}
          </div>
          <van-button
            v-if="!judged[q.id]"
            size="small"
            type="primary"
            plain
            style="margin-top: 8px"
            @click="submit(q)"
          >
            提交{{ q.type === 'multi' ? '（多选）' : '' }}
          </van-button>
          <div v-if="judged[q.id]" class="verdict" :class="{ ok: judged[q.id].correct }">
            {{ judged[q.id].correct ? '回答正确' : '回答错误' }} · {{ judged[q.id].explanation }}
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}
.stage {
  cursor: pointer;
}
.hl {
  padding: 8px 0;
  border-bottom: 1px solid #f2f3f5;
  cursor: pointer;
}
.hl:last-child {
  border: none;
}
.said {
  margin: 6px 0 4px;
  color: #1f2329;
}
.point {
  padding: 4px 0;
  font-size: 14px;
}
.dim-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
}
.scenario {
  padding: 8px 0;
  font-size: 15px;
  cursor: pointer;
}
.transcript .line {
  padding: 6px 4px;
  cursor: pointer;
  font-size: 14px;
  border-bottom: 1px solid #f7f8fa;
}
.transcript .line b {
  color: #1f6feb;
  margin-right: 6px;
}
.transcript .customer b {
  color: #ff7d00;
}
.time {
  color: #86909c;
  font-size: 12px;
  margin-right: 4px;
}
.opt {
  padding: 8px 10px;
  margin-top: 6px;
  border: 1px solid #e5e6eb;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
}
.opt.picked {
  border-color: #1f6feb;
  background: #e8f1ff;
}
.opt.right {
  border-color: #00b42a;
  background: #e8ffea;
}
.opt.wrong {
  border-color: #f53f3f;
  background: #ffece8;
}
.verdict {
  margin-top: 10px;
  font-size: 13px;
  color: #f53f3f;
}
.verdict.ok {
  color: #00b42a;
}
</style>
