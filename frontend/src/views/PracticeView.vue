<script setup lang="ts">
import { api } from '@/api'
import { useRecorder } from '@/composables/useRecorder'
import { useSpeaker } from '@/composables/useSpeaker'
import type { Message, SessionDetail } from '@/types'
import { closeToast, showConfirmDialog, showFailToast, showLoadingToast, showToast } from 'vant'
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const sid = route.params.id as string

const session = ref<SessionDetail | null>(null)
const messages = ref<Message[]>([])
const streaming = ref('')
const busy = ref(false)
const ending = ref(false)
const input = ref('')
const voiceMode = ref(false)
const asrEnabled = ref(false)
const showGoal = ref(true)
const listEl = ref<HTMLElement | null>(null)

const recorder = useRecorder()
const speaker = useSpeaker()
const turn = computed(() => messages.value.filter((m) => m.role === 'user').length)

async function scrollBottom() {
  await nextTick()
  listEl.value?.scrollTo({ top: listEl.value.scrollHeight, behavior: 'smooth' })
}

function push(role: Message['role'], content: string) {
  messages.value.push({ seq: messages.value.length, turn: turn.value, role, content })
  scrollBottom()
}

onMounted(async () => {
  try {
    const [s, sc] = await Promise.all([api.session(sid), api.speechConfig()])
    if (s.status !== 'ongoing') return router.replace(`/report/${sid}`)
    session.value = s
    messages.value = s.messages
    asrEnabled.value = sc.asr_enabled && recorder.supported
    voiceMode.value = asrEnabled.value
    scrollBottom()
    const last = s.messages.at(-1)
    if (s.messages.length === 1 && last?.role === 'customer') speaker.speak(last.content, sid)
  } catch (e) {
    showFailToast((e as Error).message)
  }
})

async function send(text: string) {
  text = text.trim()
  if (!text || busy.value) return
  busy.value = true
  input.value = ''
  showGoal.value = false
  push('user', text)
  streaming.value = ''
  let finished = false
  try {
    await api.sendMessage(sid, text, (ev) => {
      if (ev.type === 'token') {
        streaming.value += ev.text
        scrollBottom()
      } else if (ev.type === 'status') {
        ending.value = true
      } else if (ev.type === 'error') {
        showFailToast(ev.message)
      } else if (ev.type === 'done') {
        finished = ev.status !== 'ongoing'
      }
    })
    if (streaming.value) {
      const reply = streaming.value
      push('customer', reply)
      speaker.speak(reply, sid)
    }
  } catch (e) {
    showFailToast((e as Error).message)
    messages.value.pop()
    input.value = text
  } finally {
    streaming.value = ''
    busy.value = false
  }
  if (finished) {
    ending.value = true
    setTimeout(() => router.replace(`/report/${sid}`), 1200)
  }
}

async function onPressStart() {
  if (busy.value) return
  speaker.stop()
  try {
    await recorder.start()
  } catch {
    showFailToast('无法使用麦克风，请检查权限')
  }
}

async function onPressEnd() {
  if (!recorder.recording.value) return
  const result = await recorder.stop()
  if (!result) return showToast('说话时间太短')
  showLoadingToast({ message: '识别中…', duration: 0, forbidClick: true })
  try {
    const { text } = await api.asr(result.blob, result.durationMs, sid)
    closeToast()
    if (!text) return showToast('没听清，再说一次')
    await send(text)
  } catch (e) {
    showFailToast((e as Error).message)
  }
}

async function askHint() {
  if (busy.value) return
  busy.value = true
  try {
    const { hint } = await api.hint(sid)
    push('hint', hint)
  } catch (e) {
    showFailToast((e as Error).message)
  } finally {
    busy.value = false
  }
}

async function endPractice() {
  if (busy.value) return
  try {
    await showConfirmDialog({ title: '结束对练', message: '确定结束并生成评分报告吗？' })
  } catch {
    return
  }
  speaker.stop()
  ending.value = true
  try {
    await api.end(sid)
    router.replace(`/report/${sid}`)
  } catch (e) {
    ending.value = false
    showFailToast((e as Error).message)
  }
}
</script>

<template>
  <div class="practice">
    <van-nav-bar
      :title="session?.persona ? `${session.persona.name} · ${session.persona.role}` : '对练中'"
      left-arrow
      @click-left="router.push('/')"
    >
      <template #right>
        <van-icon :name="speaker.enabled.value ? 'volume-o' : 'volume'" size="20" @click="speaker.toggle" />
      </template>
    </van-nav-bar>

    <div v-if="session && showGoal" class="goal" @click="showGoal = false">
      <b>目标：</b>{{ session.goal }}
      <div v-if="session.opening_tip" class="tip">提示：{{ session.opening_tip }}</div>
    </div>

    <div ref="listEl" class="list">
      <template v-for="m in messages" :key="m.seq">
        <div v-if="m.role === 'hint'" class="hint"><van-icon name="bulb-o" /> 教练提示：{{ m.content }}</div>
        <div v-else class="msg" :class="m.role">
          <div class="avatar">{{ m.role === 'customer' ? session?.persona?.name.slice(0, 1) : '我' }}</div>
          <div class="bubble">{{ m.content }}</div>
        </div>
      </template>
      <div v-if="busy && !streaming && messages.at(-1)?.role === 'user'" class="msg customer">
        <div class="avatar">{{ session?.persona?.name.slice(0, 1) }}</div>
        <div class="bubble typing"><van-loading size="16" /> 对方正在思考…</div>
      </div>
      <div v-if="streaming" class="msg customer">
        <div class="avatar">{{ session?.persona?.name.slice(0, 1) }}</div>
        <div class="bubble">{{ streaming }}</div>
      </div>
    </div>

    <div class="toolbar">
      <div class="actions">
        <span class="muted">第 {{ turn }} 轮</span>
        <div>
          <van-button size="small" round icon="bulb-o" :disabled="busy" @click="askHint">求助</van-button>
          <van-button size="small" round type="danger" plain :disabled="busy" @click="endPractice">结束</van-button>
        </div>
      </div>
      <div class="input-row">
        <van-icon
          v-if="asrEnabled"
          :name="voiceMode ? 'comment-o' : 'audio'"
          size="26"
          class="switch"
          @click="voiceMode = !voiceMode"
        />
        <button
          v-if="voiceMode"
          class="talk"
          :class="{ active: recorder.recording.value }"
          :disabled="busy"
          @touchstart.prevent="onPressStart"
          @touchend.prevent="onPressEnd"
          @touchcancel.prevent="recorder.cancel"
          @mousedown.prevent="onPressStart"
          @mouseup.prevent="onPressEnd"
        >
          {{ recorder.recording.value ? '松开 发送' : '按住 说话' }}
        </button>
        <template v-else>
          <van-field
            v-model="input"
            class="text"
            rows="1"
            autosize
            type="textarea"
            maxlength="500"
            placeholder="输入你要说的话"
            :disabled="busy"
            @keydown.enter.exact.prevent="send(input)"
          />
          <van-button type="primary" round size="small" :disabled="busy || !input.trim()" @click="send(input)">
            发送
          </van-button>
        </template>
      </div>
    </div>

    <van-overlay :show="ending" class="ending">
      <div class="ending-box">
        <van-loading size="36" vertical color="#fff">AI 教练正在评分…</van-loading>
      </div>
    </van-overlay>
  </div>
</template>

<style scoped>
.practice {
  display: flex;
  flex-direction: column;
  height: 100vh;
  height: 100dvh;
}
.goal {
  margin: 8px 12px 0;
  padding: 10px 12px;
  background: #e8f1ff;
  border-radius: 10px;
  font-size: 13px;
  color: #1d4ed8;
  line-height: 1.6;
}
.goal .tip {
  color: #d25f00;
}
.list {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}
.msg {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 14px;
}
.msg.user {
  flex-direction: row-reverse;
}
.avatar {
  flex: none;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #ffece8;
  color: #f53f3f;
  line-height: 36px;
  text-align: center;
  font-weight: 600;
}
.msg.user .avatar {
  background: #e8f1ff;
  color: #1f6feb;
}
.bubble {
  max-width: 72%;
  padding: 10px 12px;
  border-radius: 12px;
  background: #fff;
  font-size: 15px;
  line-height: 1.6;
  word-break: break-word;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}
.msg.user .bubble {
  background: #1f6feb;
  color: #fff;
}
.typing {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #86909c;
}
.hint {
  margin: 0 8px 14px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #fff7e8;
  color: #d25f00;
  font-size: 13px;
  line-height: 1.6;
}
.toolbar {
  background: #fff;
  border-top: 1px solid #eef0f3;
  padding: 8px 12px calc(8px + env(safe-area-inset-bottom));
}
.actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.actions .van-button {
  margin-left: 8px;
}
.input-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.switch {
  color: #4e5969;
}
.text {
  flex: 1;
  padding: 6px 10px;
  background: #f2f3f5;
  border-radius: 18px;
}
.talk {
  flex: 1;
  height: 44px;
  border: none;
  border-radius: 22px;
  background: #f2f3f5;
  font-size: 16px;
  color: #1f2329;
  user-select: none;
  -webkit-user-select: none;
  -webkit-touch-callout: none;
}
.talk.active {
  background: #1f6feb;
  color: #fff;
}
.ending {
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
