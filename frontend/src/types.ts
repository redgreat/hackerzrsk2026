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
  source_recording: { id: number; title: string }
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
  mode: 'practice' | 'exam'
  exam_attempt_id: string | null
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
  background: string
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
  red_lines?: { turn: number | null; red_line: string }[]
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

export interface RubricForm {
  name: string
  dimensions: { name: string; weight: number; good: string; bad: string }[]
  hint_penalty: number
  hint_penalty_max: number
  red_lines: string[]
  red_line_cap: number
}

export interface RubricVersion {
  version: number
  created_at: string | null
  rubric: RubricForm
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

export interface KnowledgeForm {
  category: string
  title: string
  content: string
  enabled: boolean
  tags: string[]
  scenario_ids: string[]
}

export interface KnowledgeItem extends KnowledgeForm {
  id: string
}

export interface KnowledgeBundle {
  version: 1
  scripts: KnowledgeItem[]
}

// ---------- 账号 ----------

export interface AuthConfig {
  wecom_enabled: boolean
  oauth_url: string | null
  qr_url: string | null
  dev_login_enabled: boolean
  dev_auto_login: boolean
  password_enabled: boolean
  register_enabled: boolean
  require_approval: boolean
}

export type AccountStatus = 'pending' | 'active' | 'rejected' | 'disabled'

export interface Account {
  id: number
  userid: string
  name: string
  department: string
  source: string
  status: AccountStatus
  role: 'user' | 'admin'
  has_password: boolean
  created_at: string | null
  reviewed_at: string | null
  last_login_at: string | null
}

// ---------- 优质录音 ----------

export interface TranscriptLine {
  begin_ms: number
  end_ms: number
  speaker: 'agent' | 'customer'
  text: string
}

export interface RecordingAnalysis {
  title: string
  summary: string
  customer_type: string
  outcome: string
  tags: string[]
  stages: { name: string; start_index: number }[]
  highlights: { index: number; technique: string; why: string }[]
  dimension_scores: { name: string; score: number; comment: string }[]
  compliance_issues: string[]
  learning_points: string[]
  related_scenario_ids: string[]
}

export type RecordingStatus = 'imported' | 'transcribing' | 'transcribed' | 'analyzing' | 'ready' | 'failed'

export interface RecordingCard {
  id: number
  title: string
  customer_type: string
  outcome: string | null
  summary: string | null
  tags: string[]
  duration_seconds: number | null
  status: RecordingStatus
  error: string | null
  published: boolean
  play_count: number
  created_at: string | null
  published_at: string | null
}

export interface ChoiceQuestion {
  id: number
  recording_id: number
  type: 'single' | 'multi' | 'judge'
  stem: string
  options: string[]
  answer?: number[]
  explanation?: string
  status?: 'pending' | 'approved' | 'rejected'
}

export interface ExamBankQuestion {
  id: number
  scenario_id: string
  scenario_name: string
  status: 'pending' | 'approved' | 'archived'
  topic: string
  stem: string
  options: string[]
  answer: number[]
  explanation: string
}

export interface RecordingDetail extends RecordingCard {
  audio_url: string
  transcript: TranscriptLine[]
  analysis: RecordingAnalysis | null
  questions: ChoiceQuestion[]
  related_scenarios?: { id: string; name: string }[]
  source_key?: string
  learning_note: string
  extracted_scenarios: { id: string; name: string }[]
  transcript_snapshot_id?: number | null
  source_transcript?: { seq: number; channel: number; text: string }[]
  learning_transcript?: { seq: number; speaker: string; text: string }[]
  practice_candidates?: {
    id: string; name: string; status: 'pending' | 'approved' | 'archived'; yaml?: string
    source_seqs?: number[]; transcript_snapshot_id?: number
  }[]
}

export interface RecordingPage extends Paged<RecordingCard & Pick<RecordingDetail, 'extracted_scenarios'>> {
  customer_types: { name: string; count: number }[]
}

export interface AdminRecordingPage extends Paged<RecordingCard & { pending_questions: number }> {
  can_clear_recordings: boolean
  status_counts: Record<string, number>
}

// ---------- 考试 ----------

export type SectionType = 'quiz' | 'listening' | 'roleplay'

export interface PaperCard {
  id: string
  name: string
  kind: 'exam' | 'self_test'
  description: string
  pass_score: number
  time_limit_minutes: number | null
  max_attempts: number | null
  sections: { type: SectionType; title: string; weight: number }[]
  attempts: number
  best_score: number | null
  passed: boolean
  ongoing_attempt_id: string | null
}

export interface AttemptSummary {
  id: string
  paper_id: string
  paper_name: string
  kind: 'exam' | 'self_test'
  status: 'in_progress' | 'submitted'
  score: number | null
  passed: boolean | null
  started_at: string | null
  deadline_at: string | null
  submitted_at: string | null
}

export interface QuizItem {
  key: string
  type: 'single' | 'multi' | 'judge'
  stem: string
  options: string[]
  chosen: number[]
  recording?: { id: number; title: string; audio_url: string; duration_seconds: number | null }
  answer?: number[]
  explanation?: string
  credit?: number | null
}

export interface RoleplayItem {
  key: string
  scenario_id: string
  scenario_name: string
  session_id: string | null
  session_status: string | null
  report_ready: boolean
  score: number | null
}

export type AttemptSection =
  | { type: 'quiz' | 'listening'; title: string; weight: number; items: QuizItem[] }
  | { type: 'roleplay'; title: string; weight: number; items: RoleplayItem[] }

export interface AttemptDetail extends AttemptSummary {
  pass_score: number | null
  time_limit_minutes: number | null
  server_time: string
  revealed: boolean
  result: { total: number; sections: { title: string; type: SectionType; weight: number; score: number }[] } | null
  sections: AttemptSection[]
  user?: { id: number; userid: string; name: string; department: string }
}

export interface AdminAttempt extends AttemptSummary {
  user: { id: number; userid: string; name: string; department: string }
}
