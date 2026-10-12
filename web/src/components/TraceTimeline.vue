<script setup lang="ts">
import { ChevronRightIcon, ShieldIcon, SparklesIcon, WrenchIcon } from '@lucide/vue'
import { computed, onUnmounted, ref, shallowRef } from 'vue'
import JsonBlock from '@/components/JsonBlock.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { formatCost, formatDuration, formatTokens, STOP_REASON_LABELS } from '@/lib/format'
import type { Step } from '@/lib/types'
import { cn } from '@/lib/utils'
import type { RunTrace } from '@/stores/traces'

const props = defineProps<{ trace: RunTrace }>()

const now = shallowRef(new Date())
const timer = setInterval(() => {
  if (live.value) now.value = new Date()
}, 250)
onUnmounted(() => clearInterval(timer))

const expanded = ref<Set<string>>(new Set())

const TYPE_META = {
  llm_call: { label: '模型调用', icon: SparklesIcon, bar: 'bg-violet-500/70' },
  tool_call: { label: '工具调用', icon: WrenchIcon, bar: 'bg-sky-500/70' },
  guardrail: { label: '护栏', icon: ShieldIcon, bar: 'bg-amber-500/70' },
} as const

const GUARDRAIL_LABELS: Record<string, string> = {
  confirmation_required: '等待用户确认',
  tool_blocked: '工具被拦截',
  max_steps: '达到最大步数',
  consecutive_failures: '连续失败熔断',
  run_timeout: '运行时间到上限',
}

const run = computed(() => props.trace.run)
const startMs = computed(() => Date.parse(run.value.started_at))

const live = computed(() => run.value.status === 'running' || run.value.status === 'awaiting_confirmation')

function endMs(step: Step) {
  if (step.ended_at) return Date.parse(step.ended_at)
  return now.value.getTime()
}

const totalMs = computed(() => {
  if (run.value.duration_ms != null && !live.value) return Math.max(run.value.duration_ms, 1)
  const ends = props.trace.steps.map(endMs)
  return Math.max(now.value.getTime() - startMs.value, ...ends.map((e) => e - startMs.value), 1)
})

function bar(step: Step) {
  const left = ((Date.parse(step.started_at) - startMs.value) / totalMs.value) * 100
  const width = ((endMs(step) - Date.parse(step.started_at)) / totalMs.value) * 100
  return { left: `${Math.max(0, Math.min(left, 100))}%`, width: `max(${Math.max(width, 0)}%, 3px)` }
}

function stepDuration(step: Step) {
  if (step.duration_ms != null) return step.duration_ms
  return endMs(step) - Date.parse(step.started_at)
}

function title(step: Step) {
  if (step.type === 'guardrail') return GUARDRAIL_LABELS[step.name] ?? step.name
  return step.name
}

function toggle(id: string) {
  const next = new Set(expanded.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expanded.value = next
}

const stats = computed(() => [
  { label: '耗时', value: formatDuration(live.value ? totalMs.value : run.value.duration_ms) },
  { label: '模型调用', value: String(run.value.llm_calls) },
  { label: '工具调用', value: String(run.value.tool_calls) },
  { label: 'Token 入 / 出', value: `${formatTokens(run.value.input_tokens)} / ${formatTokens(run.value.output_tokens)}` },
  { label: '费用估算', value: formatCost(run.value.cost_cny) },
])
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center gap-2">
      <StatusBadge :status="run.status" />
      <span v-if="run.stop_reason" class="text-xs text-muted-foreground">
        {{ STOP_REASON_LABELS[run.stop_reason] ?? run.stop_reason }}
      </span>
      <span v-if="run.error" class="text-xs text-destructive">{{ run.error }}</span>
    </div>

    <div class="grid grid-cols-5 gap-px overflow-hidden rounded-xl bg-border ring-1 ring-border">
      <div v-for="s in stats" :key="s.label" class="bg-background px-3 py-2.5">
        <div class="text-[11px] text-muted-foreground">{{ s.label }}</div>
        <div class="mt-0.5 text-[13px] font-medium tabular-nums">{{ s.value }}</div>
      </div>
    </div>

    <ol class="space-y-1.5">
      <li v-for="step in trace.steps" :key="step.id" class="rounded-xl border bg-background">
        <button class="w-full px-3 pt-2.5 pb-2 text-left" @click="toggle(step.id)">
          <div class="flex items-center gap-2">
            <ChevronRightIcon
              :class="cn('size-3.5 shrink-0 text-muted-foreground transition-transform', expanded.has(step.id) && 'rotate-90')"
            />
            <component :is="TYPE_META[step.type].icon" class="size-3.5 shrink-0 text-muted-foreground" />
            <span class="text-[11px] text-muted-foreground">{{ TYPE_META[step.type].label }}</span>
            <span class="truncate font-mono text-[12.5px] font-medium">{{ title(step) }}</span>
            <StatusBadge :status="step.status" />
            <span class="flex-1" />
            <span v-if="step.input_tokens != null" class="text-[11px] tabular-nums text-muted-foreground">
              {{ formatTokens(step.input_tokens) }}→{{ formatTokens(step.output_tokens) }}
            </span>
            <span class="w-16 text-right text-[12px] tabular-nums text-muted-foreground">
              {{ formatDuration(stepDuration(step)) }}
            </span>
          </div>
          <div class="relative mt-2 ml-5.5 h-1.5 rounded-full bg-muted">
            <div
              :class="cn('absolute inset-y-0 rounded-full', TYPE_META[step.type].bar, step.status === 'running' && 'animate-pulse')"
              :style="bar(step)"
            />
          </div>
        </button>
        <div v-if="expanded.has(step.id)" class="border-t px-3 py-3">
          <p v-if="step.error" class="mb-2 rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {{ step.error }}
          </p>
          <Tabs default-value="input">
            <TabsList class="h-8">
              <TabsTrigger value="input" class="text-xs">输入</TabsTrigger>
              <TabsTrigger value="output" class="text-xs">输出</TabsTrigger>
              <TabsTrigger value="attributes" class="text-xs">属性</TabsTrigger>
            </TabsList>
            <TabsContent value="input"><JsonBlock :value="step.input" /></TabsContent>
            <TabsContent value="output"><JsonBlock :value="step.output" /></TabsContent>
            <TabsContent value="attributes">
              <JsonBlock :value="{ ...step.attributes, cost_cny: step.cost_cny, seq: step.seq }" />
            </TabsContent>
          </Tabs>
        </div>
      </li>
      <li v-if="!trace.steps.length" class="rounded-xl border border-dashed px-3 py-6 text-center text-xs text-muted-foreground">
        还没有步骤
      </li>
    </ol>
  </div>
</template>
