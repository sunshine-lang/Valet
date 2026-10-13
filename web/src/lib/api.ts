import type {
  AgentConfig,
  ChatSession,
  ModelInfo,
  ProviderInfo,
  Run,
  SessionDetail,
  ScheduledTask,
  SkillDetail,
  SkillInfo,
  Step,
  StreamEvent,
  ToolInfo,
  Usage,
  WorkspaceFile,
} from './types'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res))
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') return body.detail
    if (typeof body.detail?.message === 'string') return body.detail.message
    return JSON.stringify(body.detail ?? body)
  } catch {
    return `${res.status} ${res.statusText}`
  }
}

/** 以 POST 发起请求并逐个解析 SSE 事件（EventSource 只支持 GET）。 */
async function streamEvents(
  path: string,
  body: unknown,
  onEvent: (e: StreamEvent) => void,
): Promise<void> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res))
  const type = res.headers.get('content-type') ?? ''
  if (type.includes('application/json')) {
    const body = await res.json()
    if (body.user_message) onEvent({ event: 'message.completed', data: body.user_message })
    return
  }
  if (!res.body) throw new ApiError(res.status, await errorMessage(res))

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    let idx: number
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      let event = ''
      let data = ''
      for (const line of block.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7)
        else if (line.startsWith('data: ')) data += line.slice(6)
      }
      if (event && data) onEvent({ event, data: JSON.parse(data) } as StreamEvent)
    }
  }
}

export const api = {
  health: () => request<{
    ok: boolean
    name: string
    llm_provider: string
    llm_configured: boolean
    model: string
    setup_message: string | null
  }>('/api/health'),

  listSessions: () => request<ChatSession[]>('/api/sessions'),
  createSession: () => request<ChatSession>('/api/sessions', { method: 'POST' }),
  getSession: (id: string) => request<SessionDetail>(`/api/sessions/${id}`),
  deleteSession: (id: string) => request<void>(`/api/sessions/${id}`, { method: 'DELETE' }),

  sendMessage: (
    sessionId: string,
    content: string,
    attachments: { name: string; media_type: string; data_base64: string }[],
    skills: string[],
    permissionMode: 'ask' | 'assist' | 'full',
    onEvent: (e: StreamEvent) => void,
  ) =>
    streamEvents(
      `/api/sessions/${sessionId}/messages`,
      { content, attachments, skills, permission_mode: permissionMode },
      onEvent,
    ),
  listSkills: () => request<{ skills: SkillInfo[] }>('/api/skills'),
  getSkill: (name: string) => request<SkillDetail>(`/api/skills/${encodeURIComponent(name)}`),
  importSkill: (filename: string, dataBase64: string, install = true) =>
    request<{ name: string; title: string; installed: boolean }>('/api/skills/import', {
      method: 'POST',
      body: JSON.stringify({ filename, data_base64: dataBase64, install }),
    }),
  installSkill: (name: string) =>
    request<{ installed: string[] }>(`/api/skills/${encodeURIComponent(name)}/install`, {
      method: 'POST',
    }),
  removeSkill: (name: string) =>
    request<{ removed: string }>(`/api/skills/${encodeURIComponent(name)}/remove`, {
      method: 'POST',
    }),
  uninstallSkill: (name: string) =>
    request<{ installed: string[] }>(`/api/skills/${encodeURIComponent(name)}/uninstall`, {
      method: 'POST',
    }),
  listFiles: (sessionId: string) =>
    request<{ files: WorkspaceFile[] }>(`/api/sessions/${sessionId}/files`),
  confirm: (
    runId: string,
    toolCallId: string,
    choice: 'once' | 'session' | 'reject',
    onEvent: (e: StreamEvent) => void,
  ) => streamEvents(`/api/runs/${runId}/confirm`, { tool_call_id: toolCallId, choice }, onEvent),
  cancelRun: (runId: string) =>
    request<{ cancelled: boolean }>(`/api/runs/${runId}/cancel`, { method: 'POST' }),

  listRuns: (params: { status?: string; limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== '') q.set(k, String(v))
    return request<{ total: number; items: Run[] }>(`/api/runs?${q}`)
  },
  getRun: (id: string) => request<{ run: Run; steps: Step[] }>(`/api/runs/${id}`),

  getAgentConfig: () =>
    request<{ config: AgentConfig; defaults: AgentConfig; updated_at: string | null }>(
      '/api/agent-config',
    ),
  updateAgentConfig: (config: AgentConfig & { api_key?: string }) =>
    request<{ config: AgentConfig }>('/api/agent-config', {
      method: 'PUT',
      body: JSON.stringify(config),
    }),
  testModel: (body: {
    provider: string
    api_base: string
    api_key: string
    model: string
    thinking: boolean
  }) =>
    request<{ ok: boolean }>('/api/model-config/test', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  listTools: () => request<ToolInfo[]>('/api/tools'),
  listProviders: () => request<ProviderInfo[]>('/api/providers'),
  listModels: () => request<ModelInfo[]>('/api/models'),
  usageToday: () => request<Usage>('/api/usage/today'),
  listSchedules: () => request<ScheduledTask[]>('/api/schedules'),
  createSchedule: (body: Omit<ScheduledTask, 'id' | 'next_run_at' | 'last_run_at' | 'last_session_id' | 'created_at'>) =>
    request<ScheduledTask>('/api/schedules', { method: 'POST', body: JSON.stringify(body) }),
  updateSchedule: (
    id: string,
    body: Omit<ScheduledTask, 'id' | 'next_run_at' | 'last_run_at' | 'last_session_id' | 'created_at'>,
  ) => request<ScheduledTask>(`/api/schedules/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteSchedule: (id: string) => request<void>(`/api/schedules/${id}`, { method: 'DELETE' }),
}
