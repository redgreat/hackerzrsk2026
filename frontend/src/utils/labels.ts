import type { Outcome } from '@/types'

export const OUTCOME_LABEL: Record<Outcome, string> = {
  ongoing: '进行中',
  deal: '成功推进',
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
