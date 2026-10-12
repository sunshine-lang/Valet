<script setup lang="ts">
import { ArrowLeftIcon, MessageSquareIcon } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import TraceTimeline from '@/components/TraceTimeline.vue'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { formatTime } from '@/lib/format'
import { useTraceStore } from '@/stores/traces'

const route = useRoute()
const traces = useTraceStore()
const error = ref('')

const runId = computed(() => route.params.id as string)
const trace = computed(() => traces.traces[runId.value])
const snapshot = computed(() => trace.value?.run.config_snapshot)

watch(
  runId,
  async (id) => {
    error.value = ''
    try {
      await traces.load(id)
    } catch {
      error.value = '运行不存在或加载失败'
    }
  },
  { immediate: true },
)
</script>

<template>
  <div class="space-y-6">
      <div class="flex items-center justify-between gap-3">
        <RouterLink to="/settings/runs" class="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
          <ArrowLeftIcon class="size-3.5" /> 运行记录
        </RouterLink>
        <Button v-if="trace" variant="outline" size="sm" class="rounded-lg" as-child>
          <RouterLink :to="`/c/${trace.run.session_id}`"><MessageSquareIcon /> 打开对话</RouterLink>
        </Button>
      </div>
      <p v-if="trace" class="text-sm text-muted-foreground">{{ formatTime(trace.run.started_at) }}</p>

      <p v-if="error" class="text-sm text-destructive">{{ error }}</p>

      <template v-if="trace">
        <div>
          <div class="text-[11px] text-muted-foreground">用户输入</div>
          <p class="mt-1 text-[15px] leading-7 whitespace-pre-wrap">{{ trace.run.input_text }}</p>
          <p class="mt-1 font-mono text-[11px] text-muted-foreground">{{ trace.run.id }}</p>
        </div>

        <TraceTimeline :trace="trace" />

        <section v-if="snapshot" class="rounded-2xl border p-5">
          <h2 class="text-sm font-semibold">配置快照</h2>
          <p class="mt-1 text-xs text-muted-foreground">这次运行开始时生效的配置，不含 API Key</p>
          <dl class="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 text-[13px] sm:grid-cols-3">
            <div><dt class="text-[11px] text-muted-foreground">模型</dt><dd class="font-mono">{{ snapshot.model }}</dd></div>
            <div><dt class="text-[11px] text-muted-foreground">温度</dt><dd class="font-mono">{{ snapshot.temperature }}</dd></div>
            <div><dt class="text-[11px] text-muted-foreground">最大步数</dt><dd class="font-mono">{{ snapshot.max_steps }}</dd></div>
            <div><dt class="text-[11px] text-muted-foreground">运行上限</dt><dd class="font-mono">{{ snapshot.run_timeout_s }} 秒</dd></div>
            <div><dt class="text-[11px] text-muted-foreground">空闲超时</dt><dd class="font-mono">{{ snapshot.stream_idle_s }} 秒</dd></div>
            <div><dt class="text-[11px] text-muted-foreground">连续失败上限</dt><dd class="font-mono">{{ snapshot.max_consecutive_failures }}</dd></div>
            <div class="col-span-2 sm:col-span-3">
              <dt class="text-[11px] text-muted-foreground">启用的工具</dt>
              <dd class="mt-1 flex flex-wrap gap-1.5">
                <span v-for="t in snapshot.enabled_tools" :key="t" class="rounded-md bg-muted px-1.5 py-0.5 font-mono text-[11px]">{{ t }}</span>
              </dd>
            </div>
          </dl>
          <Collapsible class="mt-4">
            <CollapsibleTrigger class="text-xs font-medium text-foreground/80 hover:text-foreground">
              展开系统提示词
            </CollapsibleTrigger>
            <CollapsibleContent>
              <pre class="mt-2 rounded-lg bg-muted/60 p-3 font-mono text-[12px] leading-relaxed whitespace-pre-wrap">{{ snapshot.system_prompt }}</pre>
            </CollapsibleContent>
          </Collapsible>
        </section>
      </template>
  </div>
</template>
