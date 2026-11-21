<script setup lang="ts">
import { api } from '@/api'
import type { AttemptDetail, QuizItem, RoleplayItem } from '@/types'
import { scoreColor } from '@/utils/labels'
import { showConfirmDialog, showFailToast, showToast } from 'vant'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const aid = route.params.id as string

const a = ref<AttemptDetail | null>(null)
const remaining = ref('')
const submitting = ref(false)
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
  if (!a.value?.deadline_at) return
  const left = Math.max(0, new Date(a.value.deadline_at).getTime() - new Date(a.value.server_time).getTime())
  const s = Math.floor(left / 1000)
  remaining.value = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

async function load() {
  try {
    a.value = await api.attempt(aid)
  } catch (e) {
    showFailToast((e as Error).message)
  }
}

onMounted(async () => {
  await load()
  timer = window.setInterval(async () => {
    if (a.value?.status === 'in_progress' && a.value.deadline_at) {
      tick()
      if (remaining.value === '0:00') await load()
    }
  }, 1000)
})
onBeforeUnmount(() => window.clearInterval(timer))

async function choose(it: QuizItem, idx: number) {
  if (submitted.value) return
  const cur = it.chosen
  it.chosen = it.type === 'multi' ? (cur.includes(idx) ? cur.filter((i) => i !== idx) : [...cur, idx]) : [idx]
  try {
    await api.saveAnswers(aid, { [it.key]: it.chosen })
  } catch (e) {
    showFailToast((e as Error).message)
  }
}

async function startRoleplay(it: RoleplayItem) {
  if (it.session_id) return router.push(`/practice/${it.session_id}`)
  try {
    const r = await api.startRoleplay(aid, it.key)
    router.push(`/practice/${r.session_id}`)
  } catch (e) {
    showFailToast((e as Error).message)
  }
}

async function submit() {
  if (submitting.value) return
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
  showToast({ message: '正在判分…', duration: 0, forbidClick: true, type: 'loading' })
  try {
    a.value = await api.submitExam(aid)
  } catch (e) {
    showFailToast((e as Error).message)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="page">
    <van-nav-bar :title="a?.paper_name || '答题'" left-arrow @click-left="router.push('/exams')" />

    <template v-if="a">
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
              <van-button v-if="!submitted" size="small" type="primary" plain round @click="startRoleplay(it)">
                {{ it.session_id ? '继续对练' : '开始对练' }}
              </van-button>
              <van-button v-else-if="it.session_id" size="small" plain round @click="router.push(`/report/${it.session_id}`)">
                看报告
              </van-button>
            </div>
            <p v-if="a.kind === 'exam'" class="muted">考试中不能使用求助提示。</p>
          </div>
        </template>
      </template>

      <div v-if="!submitted" class="bottom">
        <van-button type="primary" block round :loading="submitting" @click="submit">交卷</van-button>
      </div>
      <div v-else class="bottom">
        <van-button type="primary" block round @click="router.push('/exams')">返回考试列表</van-button>
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
