import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { toast } from 'vue-sonner'
import { api, ApiError } from '@/lib/api'
import type { Message, PendingConfirmation, Run, StreamEvent } from '@/lib/types'
import { useSessionsStore } from './sessions'
import { useTraceStore } from './traces'

export const useChatStore = defineStore('chat', () => {
  const sessionId = ref<string | null>(null)
  const messages = ref<Message[]>([])
  const runs = ref<Run[]>([])
  const pending = ref<PendingConfirmation | null>(null)
  const draft = ref<{ runId: string; text: string } | null>(null)
  const thinking = ref<{ runId: string; text: string } | null>(null)
  const activeRunId = ref<string | null>(null)
  const loading = ref(false)
  const permissionMode = ref<'ask' | 'assist' | 'full'>('assist')

  const traces = useTraceStore()
  const sessionsStore = useSessionsStore()

  const busy = computed(() => activeRunId.value !== null)
  const runsById = computed(() => Object.fromEntries(runs.value.map((r) => [r.id, r])))

  function reset() {
    sessionId.value = null
    messages.value = []
    runs.value = []
    pending.value = null
    draft.value = null
    thinking.value = null
    activeRunId.value = null
    permissionMode.value = 'assist'
  }

  async function open(id: string) {
    if (sessionId.value === id && !loading.value) return
    reset()
    sessionId.value = id
    loading.value = true
    try {
      const detail = await api.getSession(id)
      if (sessionId.value !== id) return
      messages.value = detail.messages
      runs.value = detail.runs
      pending.value = detail.pending_confirmation
      permissionMode.value = detail.session.permission_mode || 'assist'
      detail.runs.forEach((r) => traces.upsertRun(r))
    } finally {
      loading.value = false
    }
  }

  async function ensureSession(): Promise<string> {
    if (sessionId.value) return sessionId.value
    const session = await api.createSession()
    sessionId.value = session.id
    return session.id
  }

  function upsertRun(run: Run) {
    const i = runs.value.findIndex((r) => r.id === run.id)
    if (i >= 0) runs.value[i] = { ...runs.value[i], ...run }
    else runs.value.push(run)
    traces.upsertRun(run)
  }

  function handle(e: StreamEvent) {
    switch (e.event) {
      case 'run.started':
        upsertRun(e.data.run)
        messages.value.push(e.data.user_message)
        activeRunId.value = e.data.run.id
        pending.value = null
        if (e.data.user_message.seq === 1) sessionsStore.refresh()
        break
      case 'run.resumed':
        upsertRun(e.data.run)
        activeRunId.value = e.data.run.id
        pending.value = null
        break
      case 'message.delta':
        if (draft.value?.runId === e.data.run_id) draft.value.text += e.data.text
        else draft.value = { runId: e.data.run_id, text: e.data.text }
        break
      case 'message.thinking':
        if (thinking.value?.runId === e.data.run_id) thinking.value.text += e.data.text
        else thinking.value = { runId: e.data.run_id, text: e.data.text }
        break
      case 'message.completed':
        if (messages.value.some((m) => m.id === e.data.id)) break
        messages.value.push(e.data)
        if (e.data.role === 'assistant') {
          draft.value = null
          thinking.value = null
        }
        break
      case 'step.started':
      case 'step.completed':
        traces.upsertStep(e.data)
        break
      case 'confirmation.required':
        pending.value = e.data
        break
      case 'run.finished':
        upsertRun(e.data)
        activeRunId.value = null
        draft.value = null
        break
    }
  }

  async function consume(sid: string, stream: Promise<void>) {
    try {
      await stream
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : '连接中断，请稍后重试')
    } finally {
      if (sessionId.value === sid) {
        if (activeRunId.value) {
          // 流意外断开：以服务端状态为准重新加载
          sessionId.value = null
          await open(sid)
        }
        activeRunId.value = null
        draft.value = null
        thinking.value = null
      }
      sessionsStore.refresh()
      sessionsStore.refreshUsage()
    }
  }

  /** 用户切到别的会话后，旧会话的流仍在继续：追踪照常记录，但不再写入当前对话。 */
  function handlerFor(sid: string) {
    return (e: StreamEvent) => {
      if (e.event === 'step.started' || e.event === 'step.completed') traces.upsertStep(e.data)
      else if (e.event === 'run.finished') traces.upsertRun(e.data)
      if (sessionId.value === sid) handle(e)
    }
  }

  async function fileToAttachment(file: File) {
    const bytes = new Uint8Array(await file.arrayBuffer())
    let binary = ''
    const step = 0x8000
    for (let i = 0; i < bytes.length; i += step) {
      binary += String.fromCharCode(...bytes.subarray(i, i + step))
    }
    return {
      name: file.name || 'file',
      media_type: file.type || 'application/octet-stream',
      data_base64: btoa(binary),
    }
  }

  async function send(text: string, files: File[] = [], skills: string[] = []) {
    const id = await ensureSession()
    const attachments = await Promise.all(files.map(fileToAttachment))
    const steering = activeRunId.value !== null
    const stream = api.sendMessage(id, text, attachments, skills, permissionMode.value, handlerFor(id))
    if (steering) {
      try {
        await stream
      } catch (err) {
        toast.error(err instanceof ApiError ? err.message : '插话失败')
      }
      return
    }
    await consume(id, stream)
  }

  async function confirm(choice: 'once' | 'session' | 'reject') {
    const p = pending.value
    const id = sessionId.value
    if (!p || !id) return
    pending.value = null
    activeRunId.value = p.run_id
    await consume(id, api.confirm(p.run_id, p.tool_call_id, choice, handlerFor(id)))
  }

  async function cancel() {
    if (!activeRunId.value) return
    await api.cancelRun(activeRunId.value)
  }

  return {
    sessionId,
    messages,
    runs,
    runsById,
    pending,
    draft,
    thinking,
    activeRunId,
    permissionMode,
    loading,
    busy,
    reset,
    open,
    ensureSession,
    send,
    confirm,
    cancel,
  }
})
