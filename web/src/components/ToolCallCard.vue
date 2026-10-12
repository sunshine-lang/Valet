<script setup lang="ts">
import { ChevronRightIcon, LoaderCircleIcon, WrenchIcon } from '@lucide/vue'
import { computed, ref } from 'vue'
import JsonBlock from '@/components/JsonBlock.vue'
import { parseJson } from '@/lib/format'
import type { Message, ToolCall } from '@/lib/types'
import { cn } from '@/lib/utils'

const props = defineProps<{ call: ToolCall; result?: Message; awaiting?: boolean; live?: boolean }>()
const open = ref(false)

const parsedResult = computed(() => (props.result ? parseJson(props.result.content) : null))

const status = computed(() => {
  if (props.awaiting) return 'pending'
  if (!props.result) return props.live ? 'running' : 'cancelled'
  const r = parsedResult.value as Record<string, unknown> | null
  if (r && typeof r === 'object' && 'error' in r) {
    if (r.error === 'timeout') return 'timeout'
    if (r.error === 'blocked') return 'blocked'
    if (r.error === 'rejected_by_user') return 'rejected'
    if (r.error === 'interrupted') return 'cancelled'
    return 'error'
  }
  return 'ok'
})

const STATUS_LABELS: Record<string, string> = {
  running: '进行中',
  pending: '待确认',
  ok: '完成',
  error: '失败',
  timeout: '超时',
  blocked: '已拦截',
  cancelled: '已取消',
  rejected: '已拒绝',
}

const statusLabel = computed(() => STATUS_LABELS[status.value] ?? status.value)

const errorMessage = computed(() => {
  const r = parsedResult.value as Record<string, unknown> | null
  return r && typeof r === 'object' && typeof r.message === 'string' && 'error' in r ? r.message : ''
})
</script>

<template>
  <div>
    <button
      class="inline-flex max-w-full items-center gap-1.5 py-0.5 text-left text-[12px] text-muted-foreground/80 transition-colors hover:text-muted-foreground"
      @click="open = !open"
    >
      <LoaderCircleIcon v-if="status === 'running'" class="size-3 shrink-0 animate-spin" />
      <WrenchIcon v-else class="size-3 shrink-0" />
      <span class="font-mono">{{ call.name }}</span>
      <span>·</span>
      <span>{{ statusLabel }}</span>
      <ChevronRightIcon :class="cn('size-3 shrink-0 transition-transform', open && 'rotate-90')" />
      <span v-if="errorMessage" class="min-w-0 truncate">{{ errorMessage }}</span>
    </button>
    <div v-if="open" class="mt-1.5 space-y-2 pl-4">
      <div>
        <div class="mb-1 text-[11px] font-medium text-muted-foreground">参数</div>
        <JsonBlock :value="call.arguments" />
      </div>
      <div v-if="result">
        <div class="mb-1 text-[11px] font-medium text-muted-foreground">结果</div>
        <JsonBlock :value="result.content" />
      </div>
    </div>
  </div>
</template>
