<script setup lang="ts">
import { RefreshCwIcon } from '@lucide/vue'
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import StatusBadge from '@/components/StatusBadge.vue'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api } from '@/lib/api'
import { formatCost, formatDuration, formatTime, formatTokens, STOP_REASON_LABELS } from '@/lib/format'
import type { Run } from '@/lib/types'

const PAGE = 50
const router = useRouter()
const status = ref('all')
const runs = ref<Run[]>([])
const total = ref(0)
const loading = ref(false)

async function load(reset = true) {
  loading.value = true
  try {
    const res = await api.listRuns({
      status: status.value === 'all' ? undefined : status.value,
      limit: PAGE,
      offset: reset ? 0 : runs.value.length,
    })
    runs.value = reset ? res.items : [...runs.value, ...res.items]
    total.value = res.total
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(status, () => load())
</script>

<template>
  <div>
    <div class="mb-4 flex items-center justify-between gap-3">
      <span class="text-sm text-muted-foreground">共 {{ total }} 次</span>
      <Button variant="outline" size="icon-sm" class="rounded-lg" title="刷新" @click="load()">
        <RefreshCwIcon :class="loading && 'animate-spin'" />
      </Button>
    </div>
      <Tabs v-model="status">
        <TabsList>
          <TabsTrigger value="all">全部</TabsTrigger>
          <TabsTrigger value="completed">完成</TabsTrigger>
          <TabsTrigger value="failed">失败</TabsTrigger>
          <TabsTrigger value="cancelled">已取消</TabsTrigger>
          <TabsTrigger value="awaiting_confirmation">待确认</TabsTrigger>
        </TabsList>
      </Tabs>

      <div class="mt-4 overflow-x-auto rounded-2xl border">
        <table class="w-full min-w-[880px] text-left text-[13px]">
          <thead class="bg-muted/40 text-[11px] whitespace-nowrap text-muted-foreground">
            <tr>
              <th class="px-4 py-2.5 font-medium">时间</th>
              <th class="px-4 py-2.5 font-medium">输入</th>
              <th class="px-4 py-2.5 font-medium">状态</th>
              <th class="px-4 py-2.5 font-medium">模型</th>
              <th class="px-4 py-2.5 text-right font-medium">模型 / 工具</th>
              <th class="px-4 py-2.5 text-right font-medium">Tokens</th>
              <th class="px-4 py-2.5 text-right font-medium">费用</th>
              <th class="px-4 py-2.5 text-right font-medium">耗时</th>
            </tr>
          </thead>
          <tbody class="divide-y">
            <tr
              v-for="r in runs"
              :key="r.id"
              class="cursor-pointer transition-colors hover:bg-muted/40"
              @click="router.push(`/settings/runs/${r.id}`)"
            >
              <td class="px-4 py-2.5 whitespace-nowrap tabular-nums text-muted-foreground">{{ formatTime(r.started_at) }}</td>
              <td class="max-w-[320px] px-4 py-2.5">
                <div class="truncate">{{ r.input_text }}</div>
                <div class="truncate text-[11px] text-muted-foreground">{{ r.session_title }}</div>
              </td>
              <td class="px-4 py-2.5">
                <div class="flex items-center gap-1.5">
                  <StatusBadge :status="r.status" />
                  <span v-if="r.stop_reason && r.stop_reason !== 'final_answer'" class="text-[11px] whitespace-nowrap text-muted-foreground">
                    {{ STOP_REASON_LABELS[r.stop_reason] ?? r.stop_reason }}
                  </span>
                </div>
              </td>
              <td class="px-4 py-2.5 font-mono text-xs whitespace-nowrap text-muted-foreground">{{ r.config_snapshot?.model ?? '—' }}</td>
              <td class="px-4 py-2.5 text-right tabular-nums">{{ r.llm_calls }} / {{ r.tool_calls }}</td>
              <td class="px-4 py-2.5 text-right tabular-nums">{{ formatTokens(r.input_tokens + r.output_tokens) }}</td>
              <td class="px-4 py-2.5 text-right tabular-nums">{{ formatCost(r.cost_cny) }}</td>
              <td class="px-4 py-2.5 text-right tabular-nums">{{ formatDuration(r.duration_ms) }}</td>
            </tr>
            <tr v-if="!runs.length && !loading">
              <td colspan="8" class="px-4 py-12 text-center text-sm text-muted-foreground">还没有运行记录</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="runs.length < total" class="mt-4 flex justify-center">
        <Button variant="outline" size="sm" class="rounded-lg" :disabled="loading" @click="load(false)">加载更多</Button>
      </div>
  </div>
</template>
