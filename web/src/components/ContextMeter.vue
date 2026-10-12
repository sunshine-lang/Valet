<script setup lang="ts">
import { XIcon } from '@lucide/vue'
import { computed, ref } from 'vue'
import { formatContextAmount } from '@/lib/format'

const props = defineProps<{
  limit: number
  parts: { key: string; label: string; tokens: number; dot: string; bar: string }[]
}>()

const open = defineModel<boolean>('open', { default: false })
const hovering = ref(false)

const used = computed(() => props.parts.reduce((sum, part) => sum + part.tokens, 0))
const ratio = computed(() => (props.limit > 0 ? Math.min(1, used.value / props.limit) : 0))
const percentLabel = computed(() => {
  if (props.limit <= 0) return '0.0%'
  return `${((used.value / props.limit) * 100).toFixed(1)}%`
})
const tip = computed(
  () => `${percentLabel.value} · ${formatContextAmount(used.value)} / ${formatContextAmount(props.limit)} 上下文已使用`,
)

const radius = 8
const circumference = 2 * Math.PI * radius
const dashOffset = computed(() => circumference * (1 - ratio.value))

const rows = computed(() =>
  props.parts.map((part) => {
    const share = props.limit > 0 ? (part.tokens / props.limit) * 100 : 0
    return { ...part, share }
  }),
)
const barScale = computed(() => {
  const total = rows.value.reduce((sum, row) => sum + row.share, 0)
  return total > 100 ? 100 / total : 1
})

function toggle() {
  open.value = !open.value
  hovering.value = false
}
</script>

<template>
  <div class="relative">
    <button
      type="button"
      class="flex size-8 items-center justify-center rounded-full text-muted-foreground hover:text-foreground"
      :aria-expanded="open"
      aria-label="上下文用量"
      @mouseenter="hovering = true"
      @mouseleave="hovering = false"
      @click="toggle"
    >
      <svg viewBox="0 0 24 24" class="size-5" aria-hidden="true">
        <circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="2.4" class="text-foreground/15" />
        <circle
          cx="12"
          cy="12"
          r="8"
          fill="none"
          stroke="currentColor"
          stroke-width="2.4"
          stroke-linecap="round"
          class="text-foreground/70"
          :stroke-dasharray="circumference"
          :stroke-dashoffset="dashOffset"
          transform="rotate(-90 12 12)"
        />
      </svg>
    </button>
    <div
      v-if="hovering && !open"
      class="pointer-events-none absolute bottom-full left-1/2 z-30 mb-2 -translate-x-1/2 rounded-lg bg-slate-700 px-2.5 py-1.5 text-[12px] whitespace-nowrap text-white shadow-lg"
    >
      {{ tip }}
    </div>
    <div v-if="open" class="fixed inset-0 z-10" @click="open = false" />
    <div
      v-if="open"
      class="absolute right-0 bottom-full z-20 mb-2 w-72 rounded-2xl border bg-popover p-4 text-popover-foreground shadow-xl"
    >
      <div class="flex items-center justify-between">
        <span class="text-[14px] font-medium">上下文用量</span>
        <button type="button" class="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground" title="关闭" @click="open = false">
          <XIcon class="size-4" />
        </button>
      </div>
      <div class="mt-3 flex items-baseline gap-2">
        <span class="text-[28px] leading-none font-semibold tracking-tight tabular-nums">{{ percentLabel }}</span>
        <span class="text-[13px] text-muted-foreground">已使用 {{ formatContextAmount(used) }}/ {{ formatContextAmount(limit) }}</span>
      </div>
      <div class="mt-3 flex h-2 overflow-hidden rounded-full bg-sky-100 dark:bg-sky-950/50">
        <div
          v-for="row in rows"
          :key="row.key"
          :class="row.bar"
          :style="{ width: `${row.share * barScale}%` }"
        />
      </div>
      <ul class="mt-3 space-y-2">
        <li v-for="row in rows" :key="row.key" class="flex items-center text-[13px]">
          <span :class="['size-2 shrink-0 rounded-full', row.dot]" />
          <span class="ml-2">{{ row.label }}</span>
          <span class="ml-auto tabular-nums text-muted-foreground">{{ row.share.toFixed(1) }}%</span>
        </li>
      </ul>
    </div>
  </div>
</template>
