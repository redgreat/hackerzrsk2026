export interface User {
  id: number
  userid: string
  name: string
  department: string
  is_admin: boolean
}

export interface ScenarioCard {
  id: string
  name: string
  department: string[]
  difficulty: number
  estimated_minutes: number
  max_turns: number
  tags: string[]
  summary: string
  persona: { name: string; role: string; personality: string }
}

export interface ScenarioDetail extends ScenarioCard {
  background: string
  goal: string
  opening: { speaker: 'user' | 'customer'; tip: string | null }
  rubric: { name: string; dimensions: { name: string; weight: number }[] }
}

export type Outcome = 'ongoing' | 'deal' | 'hangup' | 'max_turns' | 'user_end'

export interface Message {
  seq: number
  turn: number
  role: 'user' | 'customer' | 'hint'
  content: string
  trust_after?: number | null
  trust_delta?: number | null
  inner_thought?: string | null
}

export interface SessionSummary {
  id: string
  scenario_id: string
  scenario_name: string
  status: Outcome
  turns: number
  hints_used: number
  total_score: number | null
  cost_yuan: number
  started_at: string
  ended_at: string | null
}

export interface SessionDetail extends SessionSummary {
  persona: { name: string; role: string } | null
  goal: string
  opening_tip: string | null
  report_ready: boolean
  messages: Message[]
}

export interface InnerThought {
  turn: number
  trust_before: number
  trust_after: number
  delta: number
  thought: string
  behaviors: string[]
  resolved: string[]
}

export interface Report {
  scenario_id: string
  scenario_name: string
  rubric: string
  outcome: Outcome
  turns: number
  hints_used: number
  total_score: number
  summary: string
  dimension_scores: { name: string; score: number; comment: string }[]
  highlights: string[]
  improvements: string[]
  turn_reviews: { turn: number; user_said: string; issue: string; better_reply: string }[]
  trust_curve: number[]
  inner_thoughts: InnerThought[]
  references: string[]
}

export interface MyStats {
  practice_count: number
  avg_score: number | null
  best_score: number | null
  trend: { date: string; score: number; scenario: string }[]
  dimension_avg: { name: string; avg: number }[]
}

export interface Overview {
  finished_sessions: number
  users: number
  avg_score: number | null
  deal_rate: number | null
  avg_turns: number | null
  avg_duration_seconds: number | null
  avg_cost_yuan: number
  total_cost_yuan: number
  manual_coaching_cost_yuan: number
  cost_saving_ratio: number | null
  by_purpose: { purpose: string; calls: number; prompt_tokens: number; completion_tokens: number; cost_yuan: number; avg_latency_ms: number }[]
  by_scenario: { scenario: string; count: number; avg_score: number | null }[]
}

export type StreamEvent =
  | { type: 'token'; text: string }
  | { type: 'hint'; text: string }
  | { type: 'status'; status: Outcome }
  | { type: 'report_ready'; total_score: number }
  | { type: 'error'; message: string }
  | { type: 'done'; status: Outcome; turn: number }

export interface Paged<T> {
  total: number
  items: T[]
}

export interface AdminUser {
  id: number
  userid: string
  name: string
  department: string
  source: string
  last_login_at: string | null
  sessions: number
  avg_score: number | null
  cost_yuan: number
  last_practice_at: string | null
}

export interface AdminSession {
  id: string
  scenario_id: string
  scenario_name: string
  status: Outcome
  turns: number
  hints_used: number
  total_score: number | null
  final_trust: number | null
  prompt_tokens: number
  completion_tokens: number
  cost_yuan: number
  started_at: string | null
  ended_at: string | null
  userid: string
  user_name: string
  department: string
}

export interface AdminSessionDetail extends Omit<AdminSession, 'userid' | 'user_name' | 'department'> {
  user: { id: number; userid: string; name: string; department: string }
  report: Report | null
  messages: {
    seq: number
    turn: number
    role: 'user' | 'customer' | 'hint'
    content: string
    trust_delta: number | null
    trust_after: number | null
    inner_thought: string | null
    meta: Record<string, unknown> | null
  }[]
  usage: { purpose: string; model: string; prompt_tokens: number; completion_tokens: number; cost_yuan: number; latency_ms: number }[]
}

export interface UsageRow {
  id: number
  session_id: string | null
  user_id: number | null
  purpose: string
  model: string
  prompt_tokens: number
  completion_tokens: number
  audio_seconds: number
  tts_chars: number
  cost_yuan: number
  latency_ms: number
  created_at: string | null
}

export interface UsagePage extends Paged<UsageRow> {
  daily: { day: string; calls: number; cost_yuan: number; tokens: number }[]
}

export interface TrendPoint {
  day: string
  sessions: number
  avg_score: number | null
  cost_yuan: number
}

export interface AdminScenario {
  id: string
  name: string
  department: string[]
  difficulty: number
  max_turns: number
  summary: string
  goal: string
  background: string
  persona: {
    name: string
    role: string
    personality: string
    speaking_style: string
    background: string
    budget: string | null
    hidden_needs: string[]
    objections: { id: string; text: string; key: boolean; resolve_hints: string[] }[]
  }
  state_rules: { initial_trust: number; deal_threshold: number; hangup_threshold: number; min_turns_to_deal: number }
  scoring: string
  rubric: { name: string; dimensions: { name: string; weight: number; good: string; bad: string }[] }
}

export interface KnowledgeItem {
  id: number
  source: string
  title: string
  tags: string[]
  scenario_ids: string[]
  has_embedding: boolean
  preview: string
}
