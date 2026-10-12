<script setup lang="ts">
import {
  ActivityIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  ClapperboardIcon,
  CloudSunIcon,
  GitCompareIcon,
  NewspaperIcon,
} from '@lucide/vue'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AgentOrb from '@/components/AgentOrb.vue'
import Composer from '@/components/Composer.vue'
import ConfirmationCard from '@/components/ConfirmationCard.vue'
import MarkdownText from '@/components/MarkdownText.vue'
import PageHeader from '@/components/PageHeader.vue'
import RunActivity from '@/components/RunActivity.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import ToolCallCard from '@/components/ToolCallCard.vue'
import TraceDrawer from '@/components/TraceDrawer.vue'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { formatCost, formatTokens, STOP_REASON_LABELS } from '@/lib/format'
import type { AgentConfig, Message, ProviderInfo, Run, ToolInfo, WorkspaceFile } from '@/lib/types'
import { useChatStore } from '@/stores/chat'
import { useSessionsStore } from '@/stores/sessions'

const route = useRoute()
const router = useRouter()
const chat = useChatStore()
const sessions = useSessionsStore()

const agentConfig = ref<AgentConfig | null>(null)
const tools = ref<ToolInfo[]>([])
const catalogSkills = ref<{ name: string; title: string; description: string; source?: string; installed?: boolean }[]>([])
const providers = ref<ProviderInfo[]>([])
const models = computed(() => {
  const config = agentConfig.value
  const unset = !config?.provider || (config.provider === 'custom' && !config.api_base)
  const id = unset ? 'dashscope' : config?.provider
  return providers.value.find((item) => item.id === id)?.models ?? []
})
const input = ref('')
const previewPrompt = ref('')
const composer = ref<{ focus: () => void }>()
const workspaceFiles = ref<WorkspaceFile[]>([])
const traceOpen = ref(false)
const traceRunId = ref<string | null>(null)
const scroller = ref<HTMLElement>()
const stickToBottom = ref(true)
let lastScrollTop = 0
const thinkingPref = ref<Record<string, boolean>>({})

function thinkingOpen(key: string, live: boolean) {
  if (key in thinkingPref.value) return thinkingPref.value[key]
  return live
}

function toggleThinking(key: string, live: boolean) {
  thinkingPref.value = { ...thinkingPref.value, [key]: !thinkingOpen(key, live) }
}

function onScroll() {
  const el = scroller.value
  if (!el) return
  const distance = el.scrollHeight - el.scrollTop - el.clientHeight
  const movedUp = el.scrollTop < lastScrollTop - 2
  lastScrollTop = el.scrollTop
  if (movedUp && distance > 80) stickToBottom.value = false
  else if (distance <= 80) stickToBottom.value = true
}

function scrollToBottom() {
  const el = scroller.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight })
  lastScrollTop = el.scrollTop
}

const agentName = computed(() => sessions.agentName)

const PROBES = [
  { icon: CloudSunIcon, label: '杭州天气预报', prompt: '帮我查一下杭州今天的天气' },
  { icon: GitCompareIcon, label: '查找最近代码修改', prompt: '帮我看一下最近两次改动，好像给我项目改坏了' },
  { icon: ClapperboardIcon, label: '推荐几部经典电影', prompt: '推荐几部评分比较高的高分经典电影，并说明亮点' },
  { icon: NewspaperIcon, label: '每日 AI 新闻推送', prompt: '关注当天 AI 领域的重要动态，用简体中文整理 5 条，每条写清发生了什么、为什么值得看' },
]

const emptyPlaceholder = computed(() =>
  previewPrompt.value ? '' : '问点什么，或者指向下面的推荐任务看看提示…',
)

const composerPlaceholder = computed(() => {
  if (chat.pending) return '有待确认的操作；直接发新消息会作废它'
  if (chat.busy) return '插一句，这轮结束后接着处理'
  return `给 ${agentName.value} 发消息…`
})

const sessionId = computed(() => (route.params.id as string | undefined) ?? null)
const title = computed(() => sessions.sessions.find((s) => s.id === sessionId.value)?.title ?? '新对话')
const isEmpty = computed(() => !sessionId.value && chat.messages.length === 0)

watch(
  sessionId,
  (id) => {
    traceRunId.value = null
    if (id) chat.open(id)
    else if (!chat.busy) chat.reset()
  },
  { immediate: true },
)

function charsToTokens(text: string) {
  if (!text) return 0
  return Math.ceil(text.length / 2)
}

const contextEstimate = computed(() => {
  const config = agentConfig.value
  const limit = config?.max_input_tokens && config.max_input_tokens > 0 ? config.max_input_tokens : 131_072
  const system = charsToTokens(
    [config?.system_prompt ?? '', config?.thinking_effort && config.thinking_effort !== 'off' ? '思考过程必须使用简体中文，不要用英文展开推理。' : ''].join('\n'),
  )
  const enabled = new Set(config?.enabled_tools ?? [])
  const toolTokens = tools.value
    .filter((tool) => enabled.has(tool.name))
    .reduce((sum, tool) => sum + charsToTokens(`${tool.name}\n${tool.description}\n${JSON.stringify(tool.parameters)}`), 0)
  let messages = charsToTokens(input.value) + charsToTokens(chat.draft?.text ?? '') + charsToTokens(chat.thinking?.text ?? '')
  for (const message of chat.messages) {
    messages += charsToTokens(message.content || '')
    messages += charsToTokens(message.reasoning || '')
    if (message.tool_calls) messages += charsToTokens(JSON.stringify(message.tool_calls))
  }
  const skills = catalogSkills.value.reduce(
    (sum, skill) => sum + charsToTokens(`${skill.name}：${skill.description}`),
    0,
  )
  return { limit, system, tools: toolTokens, messages, connectors: 0, skills }
})

onMounted(async () => {
  try {
    const [cfg, list, installed] = await Promise.all([
      api.getAgentConfig(),
      api.listProviders(),
      api.listSkills(),
    ])
    agentConfig.value = cfg.config
    providers.value = list
    catalogSkills.value = installed.skills.filter(
      (skill) => skill.source === 'builtin' || skill.source === 'user' || skill.installed,
    )
  } catch {
    agentConfig.value = null
  }
  try {
    tools.value = await api.listTools()
  } catch {
    tools.value = []
  }
})

async function patchConfig(partial: Partial<AgentConfig>) {
  if (!agentConfig.value) return
  const previous = agentConfig.value
  agentConfig.value = { ...previous, ...partial }
  try {
    const res = await api.updateAgentConfig(agentConfig.value)
    agentConfig.value = res.config
  } catch {
    agentConfig.value = previous
  }
}

interface RunGroup {
  key: string
  run: Run | undefined
  user: Message
  assistant: Message[]
}

const toolResults = computed(() => {
  const map: Record<string, Message> = {}
  for (const m of chat.messages) if (m.role === 'tool' && m.tool_call_id) map[m.tool_call_id] = m
  return map
})

const groups = computed<RunGroup[]>(() => {
  const out: RunGroup[] = []
  for (const m of chat.messages) {
    if (m.role === 'user') {
      out.push({ key: m.id, run: m.run_id ? chat.runsById[m.run_id] : undefined, user: m, assistant: [] })
    } else if (m.role === 'assistant') {
      out.at(-1)?.assistant.push(m)
    }
  }
  return out
})

const latestRunId = computed(() => chat.runs.at(-1)?.id ?? null)

function isLive(g: RunGroup) {
  return !!g.run && g.run.id === chat.activeRunId
}

function isWorking(g: RunGroup) {
  if (isLive(g)) return true
  const status = g.run?.status
  return status === 'running' || status === 'awaiting_confirmation'
}

function hasActivityBody(g: RunGroup) {
  if (g.assistant.some((m) => m.reasoning || (m.tool_calls?.length ?? 0) > 0)) return true
  return chat.thinking?.runId === g.run?.id
}

function openTrace(runId: string | null) {
  traceRunId.value = runId
  traceOpen.value = true
}

const outputs = computed(() => workspaceFiles.value.filter((file) => file.zone === 'outputs'))

async function refreshFiles() {
  const id = sessionId.value ?? chat.sessionId
  if (!id) {
    workspaceFiles.value = []
    return
  }
  try {
    workspaceFiles.value = (await api.listFiles(id)).files
  } catch {
    workspaceFiles.value = []
  }
}

function skillTitle(name: string) {
  return catalogSkills.value.find((skill) => skill.name === name)?.title ?? name
}

async function submit(text: string, files: File[] = [], skills: string[] = []) {
  stickToBottom.value = true
  if (!sessionId.value) {
    const id = await chat.ensureSession()
    router.replace(`/c/${id}`)
    sessions.refresh()
  }
  await chat.send(text, files, skills)
  await refreshFiles()
}

function previewProbe(prompt: string) {
  if (input.value.trim()) return
  previewPrompt.value = prompt
}

function clearProbePreview() {
  previewPrompt.value = ''
}

function useProbe(prompt: string) {
  input.value = prompt
  previewPrompt.value = ''
  nextTick(() => composer.value?.focus())
}

watch(sessionId, () => {
  refreshFiles()
})
watch(
  () => chat.busy,
  (busy) => {
    if (!busy) refreshFiles()
  },
)
watch(
  () => [chat.messages.length, chat.draft?.text.length, chat.thinking?.text.length, chat.pending?.tool_call_id],
  async () => {
    if (!stickToBottom.value) return
    await nextTick()
    scrollToBottom()
  },
)
</script>

<template>
  <PageHeader :title="isEmpty ? '新对话' : title">
    <template #actions>
      <Button
        v-if="!isEmpty"
        variant="outline"
        size="sm"
        class="rounded-lg"
        @click="openTrace(traceRunId ?? chat.activeRunId ?? latestRunId)"
      >
        <span v-if="chat.busy" class="size-1.5 animate-pulse rounded-full bg-blue-500" />
        <ActivityIcon v-else />
        追踪
      </Button>
    </template>
  </PageHeader>

  <!-- 空状态 -->
  <div v-if="isEmpty" class="flex min-h-0 flex-1 flex-col items-center overflow-y-auto px-6">
    <div class="flex w-full flex-1 flex-col items-center justify-center py-12">
      <AgentOrb />
      <h2 class="mt-7 text-2xl font-semibold tracking-tight">想让 {{ agentName }} 做什么？</h2>
      <p class="mt-2 text-sm text-muted-foreground">通用智能体调试台：跑通主循环、工具调用和全链路追踪。</p>
      <div class="mt-8 w-full max-w-2xl">
        <Composer
          ref="composer"
          v-model="input"
          hero
          :model="agentConfig?.model"
          :models="models"
          :effort="agentConfig?.thinking_effort"
          :allow-images="agentConfig?.image_input === true"
          :skills="catalogSkills"
          :context="contextEstimate"
          :permission="chat.permissionMode"
          :preview-text="previewPrompt"
          @update:permission="chat.permissionMode = $event"
          @update:model="patchConfig({ model: $event })"
          @update:effort="patchConfig({ thinking_effort: $event as AgentConfig['thinking_effort'] })"
          :placeholder="emptyPlaceholder"
          @submit="submit"
        />
      </div>
      <div class="mt-4 flex max-w-2xl flex-wrap justify-center gap-2">
        <button
          v-for="p in PROBES"
          :key="p.label"
          class="inline-flex h-8 items-center gap-1.5 rounded-lg bg-muted px-3 text-[13px] text-foreground/80 ring-1 ring-transparent transition hover:bg-background hover:text-foreground hover:ring-border"
          @mouseenter="previewProbe(p.prompt)"
          @mouseleave="clearProbePreview"
          @click="useProbe(p.prompt)"
        >
          <component :is="p.icon" class="size-3.5 opacity-70" />
          {{ p.label }}
        </button>
      </div>
    </div>
  </div>

  <!-- 对话 -->
  <template v-else>
    <div ref="scroller" class="min-h-0 flex-1 overflow-y-auto" @scroll="onScroll">
      <div class="mx-auto max-w-3xl space-y-8 px-6 py-8">
        <p v-if="chat.loading" class="text-center text-sm text-muted-foreground">加载中…</p>

        <section v-for="g in groups" :key="g.key" class="space-y-4">
          <div class="flex justify-end">
            <div class="max-w-[80%] rounded-2xl bg-muted px-4 py-2.5 text-[14px] leading-6">
              <div v-if="g.user.attachments?.length" class="mb-2 flex flex-wrap gap-2">
                <template v-for="file in g.user.attachments" :key="file.path">
                  <a v-if="file.kind === 'image'" :href="file.url" target="_blank" class="block">
                    <img :src="file.url" :alt="file.name" class="max-h-40 max-w-full rounded-lg" />
                  </a>
                  <a
                    v-else
                    :href="file.url"
                    class="inline-flex max-w-full items-center rounded-lg bg-background px-2 py-1 text-xs"
                  >
                    <span class="truncate">{{ file.name }}</span>
                  </a>
                </template>
              </div>
              <div v-if="g.user.skill_names?.length" class="mb-1.5 flex flex-wrap gap-1">
                <span
                  v-for="name in g.user.skill_names"
                  :key="name"
                  class="rounded-md bg-background px-1.5 py-0.5 text-[11px] text-muted-foreground"
                >
                  {{ skillTitle(name) }}
                </span>
              </div>
              <p v-if="g.user.content" class="whitespace-pre-wrap">{{ g.user.content }}</p>
            </div>
          </div>

          <div class="space-y-4">
            <div class="flex items-center gap-2.5">
              <AgentOrb size="sm" :active="isLive(g)" />
              <span class="text-[15px] font-semibold tracking-tight">{{ agentName }}</span>
            </div>
            <div class="min-w-0 space-y-2.5">
              <RunActivity
                v-if="g.run"
                :working="isWorking(g)"
                :has-body="hasActivityBody(g)"
                :status="g.run.status"
                :started-at="g.run.started_at"
                :ended-at="g.run.ended_at"
                :duration-ms="g.run.duration_ms"
              >
                <template v-for="m in g.assistant" :key="m.id">
                  <div v-if="m.reasoning && g.run" class="text-[13px] text-muted-foreground">
                    <button type="button" class="inline-flex items-center gap-1 py-0.5 hover:text-foreground/70" @click="toggleThinking(m.id, false)">
                      <ChevronDownIcon v-if="thinkingOpen(m.id, false)" class="size-3.5" />
                      <ChevronRightIcon v-else class="size-3.5" />
                      深度思考
                    </button>
                    <MarkdownText v-show="thinkingOpen(m.id, false)" :source="m.reasoning" class="mt-1 text-[12px] leading-6 text-muted-foreground/80" />
                  </div>
                  <ToolCallCard
                    v-for="tc in m.tool_calls ?? []"
                    :key="tc.id"
                    :call="tc"
                    :result="toolResults[tc.id]"
                    :awaiting="chat.pending?.tool_call_id === tc.id"
                    :live="isLive(g)"
                  />
                </template>
                <div v-if="chat.thinking && g.run && chat.thinking.runId === g.run.id" class="text-[13px] text-muted-foreground">
                  <button type="button" class="inline-flex items-center gap-1 py-0.5 hover:text-foreground/70" @click="toggleThinking(`live:${g.run.id}`, true)">
                    <ChevronDownIcon v-if="thinkingOpen(`live:${g.run.id}`, true)" class="size-3.5" />
                    <ChevronRightIcon v-else class="size-3.5" />
                    深度思考
                  </button>
                  <MarkdownText v-show="thinkingOpen(`live:${g.run.id}`, true)" :source="chat.thinking.text" class="mt-1 text-[12px] leading-6 text-muted-foreground/80" />
                </div>
              </RunActivity>

              <MarkdownText
                v-for="m in g.assistant.filter((item) => item.content)"
                :key="m.id"
                :source="m.content"
                class="text-[14px] leading-7"
              />

              <MarkdownText
                v-if="chat.draft && chat.draft.runId === g.run?.id"
                :source="chat.draft.text"
                streaming
                class="text-[14px] leading-7"
              />

              <ConfirmationCard
                v-if="chat.pending && chat.pending.run_id === g.run?.id"
                :pending="chat.pending"
                :disabled="chat.busy"
                @decide="chat.confirm"
              />

              <p
                v-if="g.run?.status === 'failed' && g.run.error"
                class="rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive"
              >
                {{ g.run.error }}
              </p>

              <div v-if="g.run && !isLive(g)" class="flex flex-wrap items-center gap-2 pt-1 text-[11.5px] text-muted-foreground">
                <StatusBadge v-if="g.run.status !== 'completed' || g.run.stop_reason !== 'final_answer'" :status="g.run.status" />
                <span v-if="g.run.stop_reason && g.run.stop_reason !== 'final_answer'">
                  {{ STOP_REASON_LABELS[g.run.stop_reason] ?? g.run.stop_reason }}
                </span>
                <span class="tabular-nums">{{ formatTokens(g.run.input_tokens + g.run.output_tokens) }} tokens</span>
                <span>·</span>
                <span class="tabular-nums">{{ formatCost(g.run.cost_cny) }}</span>
                <button class="ml-1 font-medium text-foreground/80 underline-offset-4 hover:underline" @click="openTrace(g.run.id)">
                  查看追踪
                </button>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>

    <div class="mx-auto w-full max-w-3xl px-6 pb-5">
      <div v-if="outputs.length" class="mb-2 flex flex-wrap gap-2">
        <a
          v-for="file in outputs"
          :key="file.path"
          :href="`/api/sessions/${sessionId}/files/content?path=${encodeURIComponent(file.path)}`"
          class="inline-flex max-w-full items-center rounded-lg bg-muted px-2.5 py-1 text-xs"
        >
          <span class="truncate">{{ file.name }}</span>
        </a>
      </div>
      <Composer
        v-model="input"
        :busy="chat.busy"
        :model="agentConfig?.model"
        :models="models"
        :effort="agentConfig?.thinking_effort"
        :allow-images="agentConfig?.image_input === true"
        :skills="catalogSkills"
        :context="contextEstimate"
        :permission="chat.permissionMode"
        @update:permission="chat.permissionMode = $event"
        @update:model="patchConfig({ model: $event })"
        @update:effort="patchConfig({ thinking_effort: $event as AgentConfig['thinking_effort'] })"
        :placeholder="composerPlaceholder"
        @submit="submit"
        @stop="chat.cancel"
      />
    </div>
  </template>

  <TraceDrawer v-model:open="traceOpen" :run-id="traceRunId ?? chat.activeRunId ?? latestRunId" :live-run-id="chat.activeRunId" />
</template>
