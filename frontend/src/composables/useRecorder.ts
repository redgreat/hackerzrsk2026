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

  async function start() {
    if (!supported || recording.value) return
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const mimeType = MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported(m))
    recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
    chunks = []
    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data)
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
    return new Promise((resolve) => {
      if (!recorder || recorder.state === 'inactive') {
        release()
        return resolve(null)
      }
      const durationMs = performance.now() - startedAt
      recorder.onstop = () => {
        const blob = new Blob(chunks, { type: recorder?.mimeType || 'audio/webm' })
        release()
        resolve(durationMs < 600 ? null : { blob, durationMs })
      }
      recorder.stop()
    })
  }

  function cancel() {
    if (recorder && recorder.state !== 'inactive') {
      recorder.onstop = null
      recorder.stop()
    }
    release()
  }

  onBeforeUnmount(cancel)
  return { recording, supported, start, stop, cancel }
}
