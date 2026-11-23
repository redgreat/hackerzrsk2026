import type { Outcome } from '@/types'

export const OUTCOME_LABEL: Record<Outcome, string> = {
  ongoing: '进行中',
  deal: '目标达成',
  hangup: '客户挂断',
  max_turns: '轮数用完',
  user_end: '主动结束',
}

export const OUTCOME_TAG: Record<Outcome, 'primary' | 'success' | 'danger' | 'warning' | 'default'> = {
  ongoing: 'primary',
  deal: 'success',
  hangup: 'danger',
  max_turns: 'warning',
  user_end: 'default',
}

export function scoreColor(score: number | null | undefined): string {
  if (score == null) return '#86909c'
  if (score >= 85) return '#00b42a'
  if (score >= 70) return '#1f6feb'
  if (score >= 60) return '#ff7d00'
  return '#f53f3f'
}

export function formatTime(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function pct(v: number | null | undefined): string {
  return v == null ? '-' : `${(v * 100).toFixed(1)}%`
}

export const PURPOSE_LABEL: Record<string, string> = {
  customer: '客户回复',
  evaluator: '轮次评估',
  coach: '教练报告',
  hint: '求助提示',
  analyst: '录音分析',
  embedding: '知识向量',
  asr: '语音识别',
  tts: '语音合成',
}

export const OUTCOME_EL_TAG: Record<Outcome, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
  ongoing: 'primary',
  deal: 'success',
  hangup: 'danger',
  max_turns: 'warning',
  user_end: 'info',
}

export const RECORDING_STATUS: Record<string, { label: string; type: 'primary' | 'success' | 'warning' | 'danger' | 'info' }> = {
  imported: { label: '待处理', type: 'info' },
  transcribing: { label: '转写中', type: 'primary' },
  transcribed: { label: '已转写', type: 'primary' },
  analyzing: { label: '分析中', type: 'primary' },
  ready: { label: '已完成', type: 'success' },
  failed: { label: '失败', type: 'danger' },
}

export const ACCOUNT_STATUS: Record<string, { label: string; type: 'primary' | 'success' | 'warning' | 'danger' | 'info' }> = {
  pending: { label: '待审核', type: 'warning' },
  active: { label: '正常', type: 'success' },
  rejected: { label: '已驳回', type: 'danger' },
  disabled: { label: '已停用', type: 'info' },
}

export const QUESTION_TYPE: Record<string, string> = { single: '单选', multi: '多选', judge: '判断' }

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return '--:--'
  const s = Math.max(0, Math.round(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}
