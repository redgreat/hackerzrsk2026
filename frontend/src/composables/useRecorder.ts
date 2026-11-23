import { onBeforeUnmount, ref } from 'vue'

const MIME_CANDIDATES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg']

/** 按住说话：MediaRecorder 录音，松手返回音频与时长。 */
export function useRecorder(maxMs = 60_000) {
  const recording = ref(false)
  const supported = typeof window !== 'undefined' && 'MediaRecorder' in window && !!navigator.mediaDevices
  let recorder: MediaRecorder | null = null
  let stream: MediaStream | null = null
  let chunks: Blob[] = []
  let startedAt = 0
  let timer: number | undefined
  let generation = 0
  let pending = false
  let result: Promise<{ blob: Blob; durationMs: number } | null> | null = null

  async function start() {
    if (!supported || recording.value || pending) return
    const ticket = ++generation
    pending = true
    let acquired: MediaStream
    try {
      acquired = await navigator.mediaDevices.getUserMedia({ audio: true })
    } finally {
      if (ticket === generation) pending = false
    }
    if (ticket !== generation) {
      acquired.getTracks().forEach((t) => t.stop())
      return
    }
    stream = acquired
    const mimeType = MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported(m))
    try {
      recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
    } catch (error) {
      release()
      throw error
    }
    chunks = []
    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data)
    const current = recorder
    result = new Promise((resolve) => {
      current.onstop = () => {
        const durationMs = Math.min(performance.now() - startedAt, maxMs)
        const blob = new Blob(chunks, { type: current.mimeType || 'audio/webm' })
        release()
        resolve(durationMs < 600 || !blob.size ? null : { blob, durationMs })
      }
      current.onerror = () => { release(); resolve(null) }
    })
    recorder.start()
    startedAt = performance.now()
    recording.value = true
    timer = window.setTimeout(() => recorder?.state === 'recording' && recorder.stop(), maxMs)
  }

  function release() {
    stream?.getTracks().forEach((t) => t.stop())
    stream = null
    recording.value = false
    window.clearTimeout(timer)
  }

  function stop(): Promise<{ blob: Blob; durationMs: number } | null> {
    if (pending) cancel()
    const completed = result
    result = null
    if (recorder?.state === 'recording') recorder.stop()
    return completed ?? Promise.resolve(null)
  }

  function cancel() {
    generation++
    pending = false
    result = null
    if (recorder && recorder.state !== 'inactive') {
      recorder.onstop = null
      recorder.stop()
    }
    release()
  }

  onBeforeUnmount(cancel)
  return { recording, supported, start, stop, cancel }
}
