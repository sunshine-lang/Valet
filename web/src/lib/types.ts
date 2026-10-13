export type RunStatus = 'running' | 'awaiting_confirmation' | 'completed' | 'failed' | 'cancelled'

export type StepType = 'llm_call' | 'tool_call' | 'guardrail'

export type StepStatus =
  | 'running'
  | 'ok'
  | 'error'
  | 'timeout'
  | 'cancelled'
  | 'blocked'
  | 'pending'
  | 'approved'
  | 'rejected'

export interface ToolCall {
  id: string
  name: string
  arguments: string
}

export interface Attachment {
  name: string
  media_type: string
  size: number
  kind: 'image' | 'text' | 'file'
  path: string
  text_path?: string | null
  url: string
}

export interface WorkspaceFile {
  name: string
  path: string
  size: number
  kind: 'file' | 'dir'
  zone: 'uploads' | 'workspace' | 'outputs'
}

export interface Message {
  id: string
  session_id: string
  run_id: string | null
  seq: number
  role: 'user' | 'assistant' | 'tool'
  content: string
  reasoning: string | null
  tool_calls: ToolCall[] | null
  tool_call_id: string | null
  tool_name: string | null
  attachments: Attachment[] | null
  skill_names: string[] | null
  created_at: string
}

export interface AgentConfig {
  provider: string
  api_base: string
  api_key_set: boolean
  model: string
  tool_calling: boolean
  image_input: boolean
  thinking: boolean
  thinking_effort: 'off' | 'low' | 'medium' | 'high' | 'max'
  custom_protocol: boolean
  max_input_tokens: number | null
  max_output_tokens: number | null
  system_prompt: string
  temperature: number
  max_steps: number
  run_timeout_s: number
  stream_idle_s: number
  max_consecutive_failures: number
  enabled_tools: string[]
}

export interface Run {
  id: string
  session_id: string
  status: RunStatus
  stop_reason: string | null
  error: string | null
  input_text: string
  config_snapshot: Partial<AgentConfig> | null
  llm_calls: number
  tool_calls: number
  input_tokens: number
  output_tokens: number
  cost_cny: number
  started_at: string
  ended_at: string | null
  duration_ms: number | null
  session_title?: string
}

export interface Step {
  id: string
  run_id: string
  seq: number
  type: StepType
  name: string
  status: StepStatus
  input: unknown
  output: unknown
  error: string | null
  attributes: Record<string, unknown>
  input_tokens: number | null
  output_tokens: number | null
  cost_cny: number | null
  started_at: string
  ended_at: string | null
  duration_ms: number | null
}

export interface ChatSession {
  id: string
  title: string
  created_at: string
  updated_at: string
  permission_mode?: 'ask' | 'assist' | 'full'
}

export type PermissionChoice = 'once' | 'session' | 'reject'

export interface PendingConfirmation {
  run_id: string
  tool_call_id: string
  tool_name: string
  arguments: Record<string, unknown>
  reason: string
  step_id: string
  action?: string
}

export interface SessionDetail {
  session: ChatSession
  messages: Message[]
  runs: Run[]
  pending_confirmation: PendingConfirmation | null
}

export interface SkillInfo {
  name: string
  title: string
  description: string
  source: 'market' | 'builtin' | 'user'
  installed: boolean
}

export interface SkillDetail extends SkillInfo {
  body: string
}

export interface ToolInfo {
  name: string
  description: string
  parameters: JsonSchema
  requires_confirmation: boolean
  timeout_s: number
  example: boolean
  probes: string
}

export interface JsonSchema {
  type?: string
  properties?: Record<string, JsonSchema & { default?: unknown; enum?: unknown[] }>
  required?: string[]
  description?: string
  [key: string]: unknown
}

export interface ModelInfo {
  id: string
  label: string
  description: string
  input_price?: number
  output_price?: number
}

export interface ProviderInfo {
  id: string
  name: string
  base_url: string
  docs_url: string
  env_key: string
  env_key_set: boolean
  models: { id: string; label: string; description: string; tools: boolean; image: boolean }[]
}

export interface ScheduledTask {
  id: string
  name: string
  prompt: string
  effort: 'off' | 'low' | 'medium' | 'high' | 'max'
  repeat: 'interval' | 'once' | 'daily' | 'weekly' | 'biweekly' | 'monthly' | 'yearly'
  interval_minutes: number
  hour: number
  minute: number
  second: number
  weekday: number
  weekdays: number[]
  month_day: number
  month: number
  once_on: string | null
  valid_from: string | null
  valid_until: string | null
  notify_wechat: boolean
  enabled: boolean
  next_run_at: string | null
  last_run_at: string | null
  last_session_id: string | null
  created_at: string
}

export interface Usage {
  runs: number
  input_tokens: number
  output_tokens: number
  cost_cny: number
}

export type StreamEvent =
  | { event: 'run.started'; data: { run: Run; user_message: Message } }
  | { event: 'run.resumed'; data: { run: Run } }
  | { event: 'run.finished'; data: Run }
  | { event: 'message.delta'; data: { run_id: string; text: string } }
  | { event: 'message.thinking'; data: { run_id: string; text: string } }
  | { event: 'message.completed'; data: Message }
  | { event: 'step.started'; data: Step }
  | { event: 'step.completed'; data: Step }
  | { event: 'confirmation.required'; data: PendingConfirmation }
