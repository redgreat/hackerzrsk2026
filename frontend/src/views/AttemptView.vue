<script setup lang="ts">
import { api } from '@/api'
import type { AttemptDetail, QuizItem, RoleplayItem } from '@/types'
import { scoreColor } from '@/utils/labels'
import { closeToast, showConfirmDialog, showFailToast, showLoadingToast } from 'vant'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const aid = route.params.id as string
const fromHistory = route.query.from === 'history'
const returnPath = fromHistory ? '/my/exams' : '/exams'

const a = ref<AttemptDetail | null>(null)
const remaining = ref('')
const submitting = ref(false)
const saving = ref(false)
const deadlineChecked = ref(false)
let loading = false
let localDeadline: number | undefined
let timer: number | undefined

const isQuiz = (sec: AttemptDetail['sections'][number]) => sec.type !== 'roleplay'
const quizItems = (sec: AttemptDetail['sections'][number]) => sec.items as QuizItem[]
const rpItems = (sec: AttemptDetail['sections'][number]) => sec.items as RoleplayItem[]
const submitted = computed(() => a.value?.status === 'submitted')
const answered = computed(
  () => a.value?.sections.filter(isQuiz).flatMap((s) => s.items as QuizItem[]).filter((i) => i.chosen.length).length ?? 0,
)
const quizTotal = computed(() => a.value?.sections.filter(isQuiz).reduce((n, s) => n + s.items.length, 0) ?? 0)

function tick() {
  if (localDeadline === undefined) return
  const left = Math.max(0, localDeadline - performance.now())
  const s = Math.ceil(left / 1000)
  remaining.value = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

async function load() {
  if (loading || submitting.value) return
  loading = true
  try {
    a.value = await api.attempt(aid)
    localDeadline = a.value.deadline_at
      ? performance.now() + Date.parse(a.value.deadline_at) - Date.parse(a.value.server_time)
      : undefined
    tick()
  } catch (e) {
    showFailToast((e as Error).message)
  } finally {
    loading = false
  }
}

function resumeClock() {
  if (document.visibilityState === 'visible' && !submitted.value && !saving.value) void load()
}

async function leave() {
  if (saving.value || submitting.value) return
  if (a.value?.deadline_at && !submitted.value) {
    try {
      await showConfirmDialog({ title: '离开试卷', message: '离开后考试继续计时。已保存的答案可以继续作答。', confirmButtonText: '离开' })
    } catch {
      return
    }
  }
  await router.push(returnPath)
}

onMounted(async () => {
  document.addEventListener('visibilitychange', resumeClock)
  timer = window.setInterval(async () => {
    if (a.value?.status === 'in_progress' && a.value.deadline_at) {
      tick()
      if (remaining.value === '0:00' && !deadlineChecked.value && !submitting.value && !saving.value) {
        deadlineChecked.value = true
        await load()
      }
    }
  }, 1000)
  await load()
})
onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', resumeClock)
  window.clearInterval(timer)
})

async function choose(it: QuizItem, idx: number) {
  if (submitted.value || submitting.value || saving.value || remaining.value === '0:00') return
  const cur = it.chosen
  saving.value = true
  it.chosen = it.type === 'multi' ? (cur.includes(idx) ? cur.filter((i) => i !== idx) : [...cur, idx]) : [idx]
  try {
    await api.saveAnswers(aid, { [it.key]: it.chosen })
  } catch (e) {
    it.chosen = cur
    showFailToast((e as Error).message)
  } finally {
    saving.value = false
  }
}

async function startRoleplay(it: RoleplayItem) {
  if (submitting.value || remaining.value === '0:00') return
  try {
    const r = await api.startRoleplay(aid, it.key)
    router.push({ path: `/practice/${r.session_id}`, query: fromHistory ? { from: 'history' } : {} })
  } catch (e) {
    showFailToast((e as Error).message)
  }
}

async function submit() {
  if (submitting.value || saving.value) return
  try {
    await showConfirmDialog({
      title: '确认交卷',
      message:
        a.value?.kind === 'exam' ? '交卷后不能修改，进行中的对练会自动结束并评分。确定交卷吗？' : '确定交卷并查看解析吗？',
    })
  } catch {
    return
  }
  submitting.value = true
  showLoadingToast({ message: '正在判分…', duration: 0, forbidClick: true })
  try {
    a.value = await api.submitExam(aid)
  } catch (e) {
    closeToast()
    showFailToast((e as Error).message)
  } finally {
    if (submitted.value) closeToast()
    submitting.value = false
  }
}
</script>

<template>
  <div class="page">
    <van-nav-bar :title="a?.paper_name || '答题'" left-arrow @click-left="leave" />

    <template v-if="a">
      <p class="page-guide">
        {{ submitted
          ? '查看各部分得分，并按试卷设置回看标准答案和解析。'
          : '选择题会自动保存。完成各部分后交卷，限时试卷请留意倒计时。' }}
      </p>
      <div class="card head">
        <div>
          <van-tag :type="a.kind === 'exam' ? 'danger' : 'primary'">{{ a.kind === 'exam' ? '正式考试' : '自测' }}</van-tag>
          <span v-if="a.time_limit_minutes && !submitted" class="countdown">剩余 {{ remaining || '…' }}</span>
        </div>
        <div v-if="submitted && a.result" class="final">
          <b :style="{ color: scoreColor(a.score) }">{{ a.score }}</b> 分
          <van-tag :type="a.passed ? 'success' : 'danger'" style="margin-left: 6px">
            {{ a.passed ? '通过' : `未通过（及格 ${a.pass_score}）` }}
          </van-tag>
        </div>
        <div v-else class="muted">选择题 {{ answered }}/{{ quizTotal }}</div>
      </div>

      <div v-if="submitted && a.result" class="card">
        <h3>成绩明细</h3>
        <div v-for="s in a.result.sections" :key="s.title" class="sec-score">
          <span>{{ s.title }} <span class="muted">（权重 {{ s.weight }}）</span></span>
          <b :style="{ color: scoreColor(s.score) }">{{ s.score }} 分</b>
        </div>
      </div>

      <template v-for="sec in a.sections" :key="sec.title">
        <div class="section-title">{{ sec.title }}</div>

        <template v-if="isQuiz(sec)">
          <div v-for="it in quizItems(sec)" :key="it.key" class="card q">
            <div v-if="it.recording" class="rec">
              <div class="muted">请听录音后作答</div>
              <audio :src="it.recording.audio_url" controls style="width: 100%; margin-top: 4px" />
            </div>
            <div class="stem">{{ it.stem }} <van-tag v-if="it.type === 'multi'" plain type="warning">多选</van-tag></div>
            <div
              v-for="(opt, i) in it.options"
              :key="i"
              class="opt"
              :class="{
                picked: it.chosen.includes(i),
                right: a.revealed && it.answer?.includes(i),
                wrong: a.revealed && it.chosen.includes(i) && !it.answer?.includes(i),
              }"
              @click="choose(it, i)"
            >
              {{ opt }}
            </div>
            <div v-if="a.revealed && it.explanation" class="verdict" :class="{ ok: it.credit === 1 }">
              {{ it.credit === 1 ? '正确' : it.credit ? '部分得分' : '错误' }} · {{ it.explanation }}
            </div>
          </div>
        </template>

        <template v-else>
          <div v-for="it in rpItems(sec)" :key="it.key" class="card rp">
            <div class="rp-head">
              <div>
                <div class="name">{{ it.scenario_name }}</div>
                <div class="muted">
                  <template v-if="it.report_ready">已完成 · 得分 <b :style="{ color: scoreColor(it.score) }">{{ it.score }}</b></template>
                  <template v-else-if="it.session_id">对练进行中</template>
                  <template v-else>未开始</template>
                </div>
              </div>
              <van-button v-if="!submitted && !it.report_ready" size="small" type="primary" plain round :disabled="submitting || remaining === '0:00'" @click="startRoleplay(it)">
                {{ it.session_id ? '继续对练' : '开始对练' }}
              </van-button>
                <van-button v-else-if="submitted && it.report_ready && it.session_id" size="small" plain round :to="{ path: `/report/${it.session_id}`, query: fromHistory ? { from: 'history' } : {} }">
                看报告
              </van-button>
            </div>
            <p v-if="a.kind === 'exam'" class="muted">考试中不能使用求助提示。</p>
          </div>
        </template>
      </template>

      <div v-if="!submitted" class="bottom">
        <van-button type="primary" block round :loading="submitting" :disabled="saving" @click="submit">{{ deadlineChecked ? '重试交卷' : '交卷' }}</van-button>
      </div>
      <div v-else class="bottom">
        <van-button type="primary" block round :to="returnPath">{{ fromHistory ? '返回考试记录' : '返回考试列表' }}</van-button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.countdown {
  margin-left: 8px;
  color: #f53f3f;
  font-weight: 600;
}
.final {
  font-size: 15px;
}
.final b {
  font-size: 24px;
}
.sec-score {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
}
.q .stem {
  font-weight: 600;
  margin-bottom: 8px;
}
.rec {
  margin-bottom: 8px;
  padding: 8px;
  background: #f7f8fa;
  border-radius: 8px;
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
.rp .name {
  font-size: 15px;
  font-weight: 600;
}
.rp-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.bottom {
  padding: 12px;
}
</style>
