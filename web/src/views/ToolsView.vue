<script setup lang="ts">
import { ShieldCheckIcon, TimerIcon } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import { Switch } from '@/components/ui/switch'
import { api, ApiError } from '@/lib/api'
import type { AgentConfig, JsonSchema, ToolInfo } from '@/lib/types'

const tools = ref<ToolInfo[]>([])
const config = ref<AgentConfig | null>(null)
const enabled = ref<Set<string>>(new Set())

const groups = computed(() => [
  {
    title: '可用工具',
    hint: '计算、时间、联网与文件工具均执行真实操作。按需调整开关。',
    items: tools.value,
  },
].filter((group) => group.items.length))

onMounted(async () => {
  const [t, cfg] = await Promise.all([api.listTools(), api.getAgentConfig()])
  tools.value = t
  config.value = cfg.config
  enabled.value = new Set(cfg.config.enabled_tools)
})

async function toggle(name: string, on: boolean) {
  if (!config.value) return
  const set = new Set(config.value.enabled_tools)
  if (on) set.add(name)
  else set.delete(name)
  const enabledTools = tools.value.map((tool) => tool.name).filter((tool) => set.has(tool))
  const previous = config.value
  config.value = { ...previous, enabled_tools: enabledTools }
  enabled.value = new Set(enabledTools)
  try {
    const res = await api.updateAgentConfig(config.value)
    config.value = res.config
    enabled.value = new Set(res.config.enabled_tools)
  } catch (error) {
    config.value = previous
    enabled.value = new Set(previous.enabled_tools)
    toast.error(error instanceof ApiError ? error.message : '保存失败')
  }
}

function typeOf(p: JsonSchema & { enum?: unknown[] }) {
  if (p.enum) return p.enum.map((v) => JSON.stringify(v)).join(' | ')
  return p.type ?? 'any'
}

function constraints(p: Record<string, unknown>) {
  const parts: string[] = []
  if (p.minimum !== undefined) parts.push(`≥ ${p.minimum}`)
  if (p.maximum !== undefined) parts.push(`≤ ${p.maximum}`)
  if (p.minLength !== undefined) parts.push(`长度 ≥ ${p.minLength}`)
  if (p.maxLength !== undefined) parts.push(`长度 ≤ ${p.maxLength}`)
  if (p.default !== undefined) parts.push(`默认 ${JSON.stringify(p.default)}`)
  return parts.join('，')
}
</script>

<template>
  <div class="grid max-w-4xl gap-8">
    <section v-for="group in groups" :key="group.title" class="grid gap-4">
      <div>
        <h2 class="text-sm font-medium">{{ group.title }}</h2>
        <p class="mt-1 text-xs text-muted-foreground">{{ group.hint }}</p>
      </div>
      <article v-for="t in group.items" :key="t.name" class="rounded-2xl border p-5">
        <div class="flex flex-wrap items-center gap-2">
          <h3 class="font-mono text-[14px] font-semibold">{{ t.name }}</h3>
          <span v-if="t.probes" class="rounded-md bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">{{ t.example ? `示例：${t.probes}` : t.probes }}</span>
          <span
            v-if="t.requires_confirmation"
            class="inline-flex items-center gap-1 rounded-md bg-amber-500/12 px-1.5 py-0.5 text-[11px] text-amber-700 dark:text-amber-300"
          >
            <ShieldCheckIcon class="size-3" /> 执行前需用户确认
          </span>
          <span class="inline-flex items-center gap-1 rounded-md bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
            <TimerIcon class="size-3" /> 超时 {{ t.timeout_s }} 秒
          </span>
          <span class="flex-1" />
          <span class="text-xs text-muted-foreground">{{ enabled.has(t.name) ? '已启用' : '未启用' }}</span>
          <Switch :model-value="enabled.has(t.name)" @update:model-value="(on) => toggle(t.name, on === true)" />
        </div>
        <p class="mt-2 text-sm text-muted-foreground">{{ t.description }}</p>

        <table class="mt-4 w-full text-left text-[13px]">
          <thead class="text-[11px] text-muted-foreground">
            <tr class="border-b">
              <th class="py-2 pr-4 font-medium">参数</th>
              <th class="py-2 pr-4 font-medium">类型</th>
              <th class="py-2 pr-4 font-medium">说明</th>
              <th class="py-2 font-medium">约束</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(p, name) in t.parameters.properties ?? {}" :key="name" class="border-b last:border-0">
              <td class="py-2 pr-4 font-mono">
                {{ name }}<span v-if="t.parameters.required?.includes(String(name))" class="text-destructive">*</span>
              </td>
              <td class="py-2 pr-4 font-mono text-xs text-muted-foreground">{{ typeOf(p) }}</td>
              <td class="py-2 pr-4">{{ p.description }}</td>
              <td class="py-2 text-xs text-muted-foreground">{{ constraints(p) }}</td>
            </tr>
          </tbody>
        </table>
      </article>
    </section>
  </div>
</template>
