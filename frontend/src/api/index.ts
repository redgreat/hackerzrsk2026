import type {
  Account,
  AdminAttempt,
  AdminRecordingPage,
  AttemptDetail,
  AttemptSummary,
  AuthConfig,
  ChoiceQuestion,
  PaperCard,
  RecordingDetail,
  RecordingPage,
  AdminScenario,
  AdminSession,
  AdminSessionDetail,
  AdminUser,
  KnowledgeItem,
  MyStats,
  Overview,
  Paged,
  Report,
  ScenarioCard,
  ScenarioDetail,
  SessionDetail,
  SessionSummary,
  StreamEvent,
  TrendPoint,
  UsagePage,
  User,
} from '@/types'
import { get, patch, post, put, rawFetch } from './http'

type Query = Record<string, string | number | null | undefined>

function qs(q: Query): string {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(q)) if (v !== null && v !== undefined && v !== '') p.set(k, String(v))
  return p.toString()
}

interface LoginResult {
  token: string
  user: User
}

export const api = {
  authConfig: (redirectUri: string) => get<AuthConfig>(`/auth/config?redirect_uri=${encodeURIComponent(redirectUri)}`),
  register: (body: { userid: string; name: string; department: string; password: string }) =>
    post<{ status: string; message?: string; token?: string; user?: User }>('/auth/register', body),
  login: (userid: string, password: string) => post<LoginResult>('/auth/login', { userid, password }),
  changePassword: (oldPassword: string, newPassword: string) =>
    post<{ ok: boolean }>('/auth/password', { old_password: oldPassword, new_password: newPassword }),
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

  papers: () => get<PaperCard[]>('/exams'),
  myAttempts: () => get<AttemptSummary[]>('/exams/attempts'),
  startExam: (paperId: string) => post<AttemptDetail>(`/exams/${paperId}/start`),
  attempt: (id: string) => get<AttemptDetail>(`/exams/attempts/${id}`),
  saveAnswers: (id: string, answers: Record<string, number[]>) =>
    put<{ saved: number }>(`/exams/attempts/${id}/answers`, { answers }),
  startRoleplay: (id: string, key: string) => post<{ session_id: string }>(`/exams/attempts/${id}/roleplay`, { key }),
  submitExam: (id: string) => post<AttemptDetail>(`/exams/attempts/${id}/submit`),

  admin: {
    knowledgeEvents: (q: Query) => get<Paged<import('@/types').KnowledgeEventCard>>(`/admin/knowledge-events?${qs(q)}`),
    knowledgeEvent: (id: number) => get<import('@/types').KnowledgeEventDetail>(`/admin/knowledge-events/${id}`),
    reviewKnowledgeEvent: (id: number, body: import('@/types').KnowledgeReviewIn) => post<import('@/types').KnowledgeEventDetail>(`/admin/knowledge-events/${id}/review`, body),
    overview: () => get<Overview>('/admin/overview'),
    trend: (days: number) => get<TrendPoint[]>(`/admin/trend?days=${days}`),
    users: (q: Query) => get<Paged<AdminUser>>(`/admin/users?${qs(q)}`),
    sessions: (q: Query) => get<Paged<AdminSession>>(`/admin/sessions?${qs(q)}`),
    session: (id: string) => get<AdminSessionDetail>(`/admin/sessions/${id}`),
    usage: (q: Query) => get<UsagePage>(`/admin/usage?${qs(q)}`),
    scenarios: () => get<AdminScenario[]>('/admin/scenarios'),
    knowledge: () => get<KnowledgeItem[]>('/admin/knowledge'),

    accounts: (q: Query) => get<Paged<Account> & { pending: number }>(`/admin/accounts?${qs(q)}`),
    reviewAccount: (id: number, action: 'approve' | 'reject' | 'disable' | 'enable') =>
      post<Account>(`/admin/accounts/${id}/review`, { action }),
    setRole: (id: number, role: 'user' | 'admin') => post<Account>(`/admin/accounts/${id}/role`, { role }),
    resetPassword: (id: number, password: string) => post<{ ok: boolean }>(`/admin/accounts/${id}/password`, { password }),

    recordings: (q: Query) => get<AdminRecordingPage>(`/admin/recordings?${qs(q)}`),
    addRecording: (audioUrl: string, title: string) =>
      post<{ created: number }>('/admin/recordings', { audio_url: audioUrl, title }),
    importDbmcpRecordings: (callId?: number) =>
      post<{ found: number; created: number; existing: number; linked: number; missing_transcript: number; skipped_url: number }>(
        '/admin/recordings/import-dbmcp', { call_id: callId, limit: 5 },
      ),
    recording: (id: number | string) => get<RecordingDetail>(`/admin/recordings/${id}`),
    updateRecording: (
      id: number,
      body: { title?: string; customer_type?: string; tags?: string[]; published?: boolean; extracted_scenario_ids?: string[]; learning_note?: string; transcript_snapshot_id?: number },
    ) => patch<RecordingDetail>(`/admin/recordings/${id}`, body),
    recordingTranscripts: () => get<{ id: number; name: string }[]>('/admin/recording-transcripts'),
    generateRecordingPractices: (id: number, first: number, last: number) =>
      post<RecordingDetail>(`/admin/recordings/${id}/practices`, { first, last }),
    reviewRecordingPractice: (id: number, scenarioId: string, status: 'approved' | 'archived') =>
      patch<RecordingDetail>(`/admin/recordings/${id}/practices/${encodeURIComponent(scenarioId)}`, { status }),
    updateQuestion: (
      id: number,
      body: Partial<Pick<ChoiceQuestion, 'stem' | 'options' | 'answer' | 'explanation' | 'status'>>,
    ) => patch<ChoiceQuestion>(`/admin/recording-questions/${id}`, body),

    papers: () => get<(Omit<PaperCard, 'attempts' | 'best_score' | 'passed' | 'ongoing_attempt_id'> & { enabled: boolean; publication_id: number | null })[]>('/admin/exams/papers'),
    publishPaper: (id: string) => post<{ id: number; paper_id: string }>(`/admin/exams/papers/${encodeURIComponent(id)}/publish`),
    attempts: (q: Query) => get<Paged<AdminAttempt>>(`/admin/exams/attempts?${qs(q)}`),
    attempt: (id: string) => get<AttemptDetail>(`/admin/exams/attempts/${id}`),
  },

  recordings: (q: Query) => get<RecordingPage>(`/recordings?${qs(q)}`),
  recording: (id: string) => get<RecordingDetail>(`/recordings/${id}`),
  recordingPlayed: (id: number) => post<{ ok: boolean }>(`/recordings/${id}/played`),
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
