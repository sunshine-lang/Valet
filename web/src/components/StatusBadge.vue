<script setup lang="ts">
import { computed } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{ status: string; class?: string }>()

const META: Record<string, { label: string; tone: string }> = {
  running: { label: '运行中', tone: 'bg-blue-500/10 text-blue-700 dark:text-blue-300' },
  awaiting_confirmation: { label: '待确认', tone: 'bg-amber-500/12 text-amber-700 dark:text-amber-300' },
  pending: { label: '待确认', tone: 'bg-amber-500/12 text-amber-700 dark:text-amber-300' },
  completed: { label: '完成', tone: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' },
  ok: { label: '成功', tone: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' },
  approved: { label: '已批准', tone: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' },
  failed: { label: '失败', tone: 'bg-red-500/10 text-red-700 dark:text-red-300' },
  error: { label: '报错', tone: 'bg-red-500/10 text-red-700 dark:text-red-300' },
  timeout: { label: '超时', tone: 'bg-orange-500/12 text-orange-700 dark:text-orange-300' },
  blocked: { label: '已拦截', tone: 'bg-orange-500/12 text-orange-700 dark:text-orange-300' },
  cancelled: { label: '已取消', tone: 'bg-zinc-500/12 text-zinc-600 dark:text-zinc-300' },
  rejected: { label: '已拒绝', tone: 'bg-zinc-500/12 text-zinc-600 dark:text-zinc-300' },
}

const meta = computed(() => META[props.status] ?? { label: props.status, tone: 'bg-muted text-muted-foreground' })
</script>

<template>
  <span
    :class="cn('inline-flex h-5 items-center gap-1 rounded-md px-1.5 text-[11px] font-medium whitespace-nowrap', meta.tone, props.class)"
  >
    <span v-if="status === 'running'" class="size-1.5 animate-pulse rounded-full bg-current" />
    {{ meta.label }}
  </span>
</template>
