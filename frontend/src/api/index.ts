import type {
  MyStats,
  Overview,
  Report,
  ScenarioCard,
  ScenarioDetail,
  SessionDetail,
  SessionSummary,
  StreamEvent,
  User,
} from '@/types'
import { get, post, rawFetch } from './http'

interface LoginResult {
  token: string
  user: User
}

export const api = {
  authConfig: (redirectUri: string) =>
    get<{ wecom_enabled: boolean; oauth_url: string | null; dev_login_enabled: boolean }>(
      `/auth/config?redirect_uri=${encodeURIComponent(redirectUri)}`,
    ),
  wecomLogin: (code: string) => post<LoginResult>('/auth/wecom', { code }),
  devLogin: (userid: string, name: string, department: string) =>
    post<LoginResult>('/auth/dev', { userid, name, department }),
  me: () => get<User>('/auth/me'),

  scenarios: () => get<ScenarioCard[]>('/scenarios'),
  scenario: (id: string) => get<ScenarioDetail>(`/scenarios/${id}`),

  startSession: (scenarioId: string) => post<SessionDetail>('/sessions', { scenario_id: scenarioId }),
  session: (id: string) => get<SessionDetail>(`/sessions/${id}`),
  sessions: () => get<SessionSummary[]>('/sessions'),
  hint: (id: string) => post<{ hint: string }>(`/sessions/${id}/hint`),
  end: (id: string) => post<Report>(`/sessions/${id}/end`),
  report: (id: string) => get<Report>(`/sessions/${id}/report`),

  myStats: () => get<MyStats>('/stats/me'),
  overview: () => get<Overview>('/stats/overview'),

  speechConfig: () => get<{ asr_enabled: boolean; tts_enabled: boolean }>('/speech/config'),
  asr: (blob: Blob, durationMs: number, sessionId?: string) => {
    const form = new FormData()
    const ext = blob.type.includes('mp4') ? 'm4a' : blob.type.includes('ogg') ? 'ogg' : 'webm'
    form.append('file', blob, `voice.${ext}`)
    form.append('duration_ms', String(Math.round(durationMs)))
    if (sessionId) form.append('session_id', sessionId)
    return rawFetch('/speech/asr', { method: 'POST', body: form }).then((r) => r.json() as Promise<{ text: string }>)
  },
  tts: (text: string, sessionId?: string) =>
    rawFetch('/speech/tts', { method: 'POST', body: JSON.stringify({ text, session_id: sessionId }) }).then((r) =>
      r.blob(),
    ),

  /** 发送消息并以 SSE 接收客户回复流。 */
  async sendMessage(id: string, text: string, onEvent: (ev: StreamEvent) => void): Promise<void> {
    const resp = await rawFetch(`/sessions/${id}/messages`, { method: 'POST', body: JSON.stringify({ text }) })
    const reader = resp.body!.pipeThrough(new TextDecoderStream()).getReader()
    let buffer = ''
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += value
      let idx: number
      while ((idx = buffer.indexOf('\n\n')) >= 0) {
        const block = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        const data = block
          .split('\n')
          .filter((l) => l.startsWith('data:'))
          .map((l) => l.slice(5).trimStart())
          .join('\n')
        if (data) onEvent(JSON.parse(data) as StreamEvent)
      }
    }
  },
}
