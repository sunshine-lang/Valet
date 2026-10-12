<script setup lang="ts">
import {
  ActivityIcon,
  CpuIcon,
  PaletteIcon,
  SlidersHorizontalIcon,
  WrenchIcon,
  XIcon,
  type LucideIcon,
} from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import ModelConfigDrawer from '@/components/ModelConfigDrawer.vue'
import PageHeader from '@/components/PageHeader.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { useTheme } from '@/composables/useTheme'
import { api, ApiError } from '@/lib/api'
import type { AgentConfig } from '@/lib/types'
import { cn } from '@/lib/utils'
import RunDetailView from '@/views/RunDetailView.vue'
import RunsView from '@/views/RunsView.vue'
import ToolsView from '@/views/ToolsView.vue'

type SectionId = 'general' | 'appearance' | 'model' | 'tools' | 'runs'

const groups: { label: string; items: { id: SectionId; label: string; icon: LucideIcon; hint: string }[] }[] = [
  {
    label: '设置',
    items: [
      { id: 'general', label: '通用', icon: SlidersHorizontalIcon, hint: '运行步数、超时和系统提示词' },
      { id: 'appearance', label: '外观', icon: PaletteIcon, hint: '界面主题' },
    ],
  },
  {
    label: '功能',
    items: [
      { id: 'model', label: '模型', icon: CpuIcon, hint: '接口地址、API Key 和模型名称' },
      { id: 'tools', label: '工具', icon: WrenchIcon, hint: '正式工具默认打开，示例工具用来试主循环' },
    ],
  },
  {
    label: '观测',
    items: [{ id: 'runs', label: '运行记录', icon: ActivityIcon, hint: '每次对话的耗时、token 和费用' }],
  },
]

const route = useRoute()
const router = useRouter()
const { isDark, toggle } = useTheme()

const sections = groups.flatMap((group) => group.items)

const runId = computed(() => {
  const value = route.params.id
  return Array.isArray(value) ? value[0] : value
})

const section = computed(() => {
  if (runId.value || route.path.startsWith('/settings/runs')) return 'runs'
  const value = route.params.section
  const id = Array.isArray(value) ? value[0] : value
  return sections.some((item) => item.id === id) ? (id as SectionId) : 'general'
})

const current = computed(() => sections.find((item) => item.id === section.value) ?? sections[0]!)

const general = ref<AgentConfig | null>(null)
const savingGeneral = ref(false)

onMounted(async () => {
  try {
    general.value = (await api.getAgentConfig()).config
  } catch {
    toast.error('通用设置加载失败')
  }
})

async function saveGeneral() {
  if (!general.value) return
  savingGeneral.value = true
  try {
    const res = await api.updateAgentConfig(general.value)
    general.value = res.config
    toast.success('通用设置已保存')
  } catch (error) {
    toast.error(error instanceof ApiError ? error.message : '保存失败')
  } finally {
    savingGeneral.value = false
  }
}

function openSection(id: SectionId) {
  router.push(`/settings/${id}`)
}

const itemClass = (active: boolean) =>
  cn(
    'flex h-9 w-full items-center gap-2.5 rounded-lg px-2.5 text-[13px] transition-colors',
    active
      ? 'bg-sidebar-accent font-medium text-foreground shadow-xs ring-1 ring-black/5 dark:ring-white/10'
      : 'text-foreground/75 hover:bg-sidebar-accent/70 hover:text-foreground',
  )
</script>

<template>
  <div class="flex h-full bg-background text-foreground">
    <aside class="flex w-60 shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground">
      <div class="flex h-14 items-center gap-2 px-3">
        <button
          class="flex size-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-sidebar-accent hover:text-foreground"
          title="关闭设置"
          @click="router.push('/')"
        >
          <XIcon class="size-4" />
        </button>
        <span class="text-[15px] font-semibold tracking-tight">设置</span>
      </div>

      <nav class="min-h-0 flex-1 space-y-4 overflow-y-auto px-3 pb-4">
        <div v-for="group in groups" :key="group.label">
          <div class="px-2.5 pb-1 text-[11px] font-semibold tracking-wider text-muted-foreground">{{ group.label }}</div>
          <button
            v-for="item in group.items"
            :key="item.id"
            type="button"
            :class="cn(itemClass(section === item.id), 'mt-0.5')"
            @click="openSection(item.id)"
          >
            <component :is="item.icon" class="size-4" />
            {{ item.label }}
          </button>
        </div>
      </nav>
    </aside>

    <main class="flex min-w-0 flex-1 flex-col">
      <PageHeader
        :title="runId ? '运行详情' : current.label"
        :subtitle="runId ? undefined : current.hint"
      />
      <div class="min-h-0 flex-1 overflow-y-auto">
        <div :class="cn('mx-auto px-6 py-8', section === 'runs' ? 'max-w-6xl' : 'max-w-3xl')">
        <section v-if="section === 'general'" class="max-w-xl">
          <div v-if="general" class="divide-y rounded-2xl border px-5">
            <label class="flex items-center justify-between gap-6 py-4">
              <span>
                <span class="block text-sm font-medium">采样温度</span>
                <span class="mt-0.5 block text-xs text-muted-foreground">函数调用建议 0 到 0.3</span>
              </span>
              <Input v-model.number="general.temperature" type="number" min="0" max="2" step="0.05" class="w-28" />
            </label>
            <label class="flex items-center justify-between gap-6 py-4">
              <span>
                <span class="block text-sm font-medium">最大步数</span>
                <span class="mt-0.5 block text-xs text-muted-foreground">单次运行最多调用模型几次</span>
              </span>
              <Input v-model.number="general.max_steps" type="number" min="1" max="20" class="w-28" />
            </label>
            <label class="flex items-center justify-between gap-6 py-4">
              <span>
                <span class="block text-sm font-medium">运行上限（秒）</span>
                <span class="mt-0.5 block text-xs text-muted-foreground">到点后不再调用工具，用已有结果收尾。正在输出时不会被掐断</span>
              </span>
              <Input v-model.number="general.run_timeout_s" type="number" min="60" max="3600" class="w-28" />
            </label>
            <label class="flex items-center justify-between gap-6 py-4">
              <span>
                <span class="block text-sm font-medium">空闲超时（秒）</span>
                <span class="mt-0.5 block text-xs text-muted-foreground">持续有输出就不会中断。这么久没有任何新内容，才视为卡住</span>
              </span>
              <Input v-model.number="general.stream_idle_s" type="number" min="15" max="300" class="w-28" />
            </label>
            <label class="flex items-center justify-between gap-6 py-4">
              <span>
                <span class="block text-sm font-medium">连续失败上限</span>
                <span class="mt-0.5 block text-xs text-muted-foreground">工具连续失败几次后停止</span>
              </span>
              <Input v-model.number="general.max_consecutive_failures" type="number" min="1" max="10" class="w-28" />
            </label>
            <div class="py-4">
              <div class="text-sm font-medium">系统提示词</div>
              <Textarea v-model="general.system_prompt" rows="8" class="mt-2 font-mono text-[12.5px] leading-relaxed" />
            </div>
            <div class="flex justify-end py-4">
              <Button size="sm" class="rounded-lg" :disabled="savingGeneral" @click="saveGeneral">
                保存
              </Button>
            </div>
          </div>
          <p v-else class="text-sm text-muted-foreground">加载中…</p>
        </section>

        <section v-else-if="section === 'appearance'" class="max-w-xl">
          <div class="flex items-center justify-between gap-6 rounded-2xl border px-5 py-4">
            <span>
              <span class="block text-sm font-medium">深色模式</span>
              <span class="mt-0.5 block text-xs text-muted-foreground">关闭后使用浅色界面</span>
            </span>
            <Switch :model-value="isDark" @update:model-value="toggle" />
          </div>
        </section>

        <section v-else-if="section === 'model'">
          <ModelConfigDrawer />
        </section>

        <section v-else-if="section === 'tools'">
          <p class="mb-4 text-sm text-muted-foreground">正式工具默认打开。示例工具用来试主循环，默认关闭。文件只写在当前会话的目录里。</p>
          <ToolsView />
        </section>

        <section v-else>
          <RunDetailView v-if="runId" />
          <RunsView v-else />
        </section>
        </div>
      </div>
    </main>
  </div>
</template>
