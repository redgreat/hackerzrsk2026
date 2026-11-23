import { api } from '@/api'
import { onBeforeUnmount, ref } from 'vue'

/** 播放客户回复：服务端 TTS 优先，未开启时退化为浏览器 speechSynthesis。 */
export function useSpeaker() {
  const enabled = ref(localStorage.getItem('coach_voice') !== 'off')
  const serverTts = ref(false)
  let audio: HTMLAudioElement | null = null
  let generation = 0
  let objectUrl: string | null = null

  api
    .speechConfig()
    .then((c) => (serverTts.value = c.tts_enabled))
    .catch(() => {})

  function stop() {
    generation++
    audio?.pause()
    audio = null
    if (objectUrl) URL.revokeObjectURL(objectUrl)
    objectUrl = null
    if ('speechSynthesis' in window) window.speechSynthesis.cancel()
  }

  async function speak(text: string, sessionId?: string) {
    if (!enabled.value || !text) return
    stop()
    const ticket = generation
    if (serverTts.value) {
      try {
        const blob = await api.tts(text, sessionId)
        if (ticket !== generation) return
        if (blob.size) {
          objectUrl = URL.createObjectURL(blob)
          audio = new Audio(objectUrl)
          await audio.play()
          return
        }
      } catch {
        /* 退化为浏览器朗读 */
      }
    }
    if (ticket !== generation) return
    if ('speechSynthesis' in window) {
      const u = new SpeechSynthesisUtterance(text)
      u.lang = 'zh-CN'
      u.rate = 1.1
      window.speechSynthesis.speak(u)
    }
  }

  function toggle() {
    enabled.value = !enabled.value
    localStorage.setItem('coach_voice', enabled.value ? 'on' : 'off')
    if (!enabled.value) stop()
  }

  onBeforeUnmount(stop)
  return { enabled, speak, stop, toggle }
}
