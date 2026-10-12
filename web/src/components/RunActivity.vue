<script setup lang="ts">
import { ChevronDownIcon, ChevronRightIcon } from '@lucide/vue'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { formatElapsed } from '@/lib/format'
import { cn } from '@/lib/utils'

const props = defineProps<{
  working: boolean
  hasBody: boolean
  status?: string | null
  startedAt?: string | null
  endedAt?: string | null
  durationMs?: number | null
}>()

const open = ref(true)
const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | undefined

function startClock() {
  now.value = Date.now()
  if (timer) return
  timer = setInterval(() => {
    now.value = Date.now()
  }, 1000)
}

function stopClock() {
  if (!timer) return
  clearInterval(timer)
  timer = undefined
}

watch(
  () => props.working,
  (working) => {
    if (working) startClock()
    else stopClock()
  },
  { immediate: true },
)

onBeforeUnmount(stopClock)

const elapsedMs = computed(() => {
  if (!props.working) {
    if (props.durationMs != null) return props.durationMs
    if (props.startedAt && props.endedAt) {
      const span = Date.parse(props.endedAt) - Date.parse(props.startedAt)
      return Number.isFinite(span) ? Math.max(0, span) : 0
    }
    return 0
  }
  const start = props.startedAt ? Date.parse(props.startedAt) : Number.NaN
  if (!Number.isFinite(start)) return 0
  return Math.max(0, now.value - start)
})

const headline = computed(() => {
  if (props.working || props.status === 'running' || props.status === 'awaiting_confirmation') {
    return '正在努力完成任务'
  }
  if (props.status === 'failed') return '未能完成'
  if (props.status === 'cancelled') return '已取消'
  return '已完成'
})

function toggle() {
  if (!props.hasBody) return
  open.value = !open.value
}
</script>

<template>
  <div>
    <button
      type="button"
      :class="cn(
        'inline-flex items-center gap-1 py-0.5 text-left text-sm text-muted-foreground',
        hasBody && 'transition-colors hover:text-foreground/70',
      )"
      @click="toggle"
    >
      <span>{{ headline }} {{ formatElapsed(elapsedMs) }}</span>
      <ChevronDownIcon v-if="hasBody && open" class="size-3.5 shrink-0" />
      <ChevronRightIcon v-else-if="hasBody" class="size-3.5 shrink-0" />
    </button>
    <div v-show="open && hasBody" class="mt-4 space-y-3.5">
      <slot />
    </div>
  </div>
</template>
