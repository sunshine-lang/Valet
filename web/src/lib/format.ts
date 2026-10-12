export function formatElapsed(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return '0s'
  const total = Math.floor(ms / 1000)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0) return `${h}h${m}m${String(s).padStart(2, '0')}s`
  if (m > 0) return `${m}m${String(s).padStart(2, '0')}s`
  return `${s}s`
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${ms} ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(ms < 10_000 ? 2 : 1)} s`
  const m = Math.floor(ms / 60_000)
  const s = Math.round((ms % 60_000) / 1000)
  return `${m} 分 ${s} 秒`
}

export function formatTokens(n: number | null | undefined): string {
  if (n == null) return '—'
  if (n < 1000) return String(n)
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`
  return `${(n / 1_000_000).toFixed(2)}M`
}

export function formatContextAmount(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return '0'
  if (n < 1000) return String(Math.round(n))
  return `${(n / 1000).toFixed(1)}K`
}

export function formatCost(cny: number | null | undefined): string {
  if (cny == null) return '—'
  if (cny === 0) return '¥0'
  if (cny < 0.0001) return '<¥0.0001'
  if (cny < 1) return `¥${cny.toFixed(4)}`
  return `¥${cny.toFixed(2)}`
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  const time = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  if (sameDay) return time
  return `${d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })} ${time}`
}

export function prettyJson(value: unknown): string {
  if (value === undefined || value === null) return 'null'
  if (typeof value === 'string') {
    try {
      return JSON.stringify(JSON.parse(value), null, 2)
    } catch {
      return value
    }
  }
  return JSON.stringify(value, null, 2)
}

export function parseJson(value: string | null | undefined): unknown {
  if (!value) return null
  try {
    return JSON.parse(value)
  } catch {
    return value
  }
}

export const STOP_REASON_LABELS: Record<string, string> = {
  final_answer: '正常完成',
  max_steps: '达到最大步数',
  consecutive_tool_failures: '工具连续失败',
  confirmation_required: '等待确认',
  run_timeout: '到时收尾',
  stream_idle: '模型停止输出',
  user_cancelled: '用户取消',
  superseded: '被新消息打断',
  server_restart: '服务重启',
  error: '异常',
}
