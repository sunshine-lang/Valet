<script setup lang="ts">
import { ExternalLinkIcon } from '@lucide/vue'
import { computed, watch } from 'vue'
import TraceTimeline from '@/components/TraceTimeline.vue'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { formatTime } from '@/lib/format'
import { useTraceStore } from '@/stores/traces'

const props = defineProps<{ runId: string | null; liveRunId: string | null }>()
const open = defineModel<boolean>('open', { default: false })

const traces = useTraceStore()
const trace = computed(() => (props.runId ? traces.traces[props.runId] : undefined))

// 正在流式的运行由事件实时更新；其他运行打开时从服务端拉一次完整步骤
watch(
  () => [open.value, props.runId] as const,
  ([isOpen, id]) => {
    if (isOpen && id && id !== props.liveRunId) traces.load(id)
  },
  { immediate: true },
)
</script>

<template>
  <Sheet v-model:open="open">
    <SheetContent side="right" class="gap-0 p-0 data-[side=right]:w-full data-[side=right]:sm:max-w-[640px]">
      <SheetHeader class="border-b px-5 py-4">
        <SheetTitle class="text-[15px]">运行追踪</SheetTitle>
        <SheetDescription class="flex items-center gap-2 font-mono text-[11px]">
          <span>{{ runId?.slice(0, 8) ?? '—' }}</span>
          <span v-if="trace">· {{ formatTime(trace.run.started_at) }}</span>
          <RouterLink
            v-if="runId"
            :to="`/settings/runs/${runId}`"
            class="ml-auto inline-flex items-center gap-1 font-sans text-xs text-foreground/80 hover:text-foreground"
          >
            详情页 <ExternalLinkIcon class="size-3" />
          </RouterLink>
        </SheetDescription>
      </SheetHeader>
      <div class="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        <TraceTimeline v-if="trace" :trace="trace" />
        <p v-else class="py-10 text-center text-sm text-muted-foreground">
          {{ runId ? '加载中…' : '还没有运行。发一条消息后，这里会实时显示每一步。' }}
        </p>
      </div>
    </SheetContent>
  </Sheet>
</template>
