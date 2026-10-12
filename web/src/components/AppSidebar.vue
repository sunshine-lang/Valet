<script setup lang="ts">
import {
  BlocksIcon,
  CalendarClockIcon,
  ChevronDownIcon,
  ChevronsUpDownIcon,
  CircleHelpIcon,
  LibraryIcon,
  MessageSquareIcon,
  PanelLeftCloseIcon,
  PanelLeftOpenIcon,
  SettingsIcon,
  SquarePenIcon,
  Trash2Icon,
  TriangleAlertIcon,
} from '@lucide/vue'
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { formatCost, formatTokens } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useChatStore } from '@/stores/chat'
import { useSessionsStore } from '@/stores/sessions'

const DAILY_BUDGET_CNY = 1

const route = useRoute()
const router = useRouter()
const sessions = useSessionsStore()
const chat = useChatStore()
const accountOpen = ref(false)
const usageOpen = ref(false)
const collapsed = ref(localStorage.getItem('valet-sidebar') === 'collapsed')
const agentName = computed(() => sessions.agentName)
const agentInitial = computed(() => agentName.value.slice(0, 1) || 'A')

function toggleSidebar() {
  collapsed.value = !collapsed.value
  localStorage.setItem('valet-sidebar', collapsed.value ? 'collapsed' : 'expanded')
  if (collapsed.value) {
    accountOpen.value = false
    usageOpen.value = false
  }
}

const budgetLabel = computed(() => `${Math.round(budgetPct.value)}%`)

function toggleAccount() {
  accountOpen.value = !accountOpen.value
  if (!accountOpen.value) usageOpen.value = false
}

function openSettings() {
  accountOpen.value = false
  usageOpen.value = false
  router.push('/settings/model')
}

function showHelp() {
  accountOpen.value = false
  toast.message('在「设置」里填写接口地址、API Key 和模型名称。')
}

const budgetPct = computed(() =>
  Math.min(100, ((sessions.usage?.cost_cny ?? 0) / DAILY_BUDGET_CNY) * 100),
)

async function removeSession(id: string) {
  try {
    await sessions.remove(id)
    if (chat.sessionId === id) {
      chat.reset()
      router.push('/')
    }
  } catch {
    toast.error('删除失败')
  }
}

const places = [
  { to: '/skills', label: '技能', icon: BlocksIcon },
  { to: '/knowledge', label: '知识库', icon: LibraryIcon },
  { to: '/schedules', label: '定时任务', icon: CalendarClockIcon },
]

const itemClass = (active: boolean) =>
  cn(
    'flex h-9 w-full items-center gap-2.5 rounded-lg px-2.5 text-[13px] transition-colors',
    active
      ? 'bg-sidebar-accent font-medium text-foreground shadow-xs ring-1 ring-black/5 dark:ring-white/10'
      : 'text-foreground/75 hover:bg-sidebar-accent/70 hover:text-foreground',
  )
</script>

<template>
  <aside
    :class="cn(
      'flex shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground transition-[width] duration-200',
      collapsed ? 'w-16' : 'w-60',
    )"
  >
    <div :class="cn('flex h-14 items-center gap-2.5', collapsed ? 'justify-center px-2' : 'px-4')">
      <div v-if="!collapsed" class="flex size-7 items-center justify-center rounded-lg bg-foreground text-background">
        <span class="text-[13px] font-bold">{{ agentInitial }}</span>
      </div>
      <span v-if="!collapsed" class="text-[15px] font-semibold tracking-tight">{{ agentName }}</span>
      <button
        type="button"
        :class="cn(
          'flex size-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-sidebar-accent hover:text-foreground',
          !collapsed && 'ml-auto',
        )"
        :title="collapsed ? '展开侧边栏' : '收起侧边栏'"
        @click="toggleSidebar"
      >
        <PanelLeftOpenIcon v-if="collapsed" class="size-4" />
        <PanelLeftCloseIcon v-else class="size-4" />
      </button>
    </div>

    <div :class="collapsed ? 'px-2' : 'px-3'">
      <RouterLink
        to="/"
        :class="cn(itemClass(route.path === '/'), collapsed && 'justify-center px-0')"
        :title="collapsed ? '新对话' : undefined"
        @click="chat.reset()"
      >
        <SquarePenIcon class="size-4" />
        <span v-if="!collapsed">新对话</span>
      </RouterLink>
      <RouterLink
        v-for="item in places"
        :key="item.to"
        :to="item.to"
        :title="collapsed ? item.label : undefined"
        :class="cn(itemClass(route.path === item.to), 'mt-0.5', collapsed && 'justify-center px-0')"
      >
        <component :is="item.icon" class="size-4" />
        <span v-if="!collapsed">{{ item.label }}</span>
      </RouterLink>
    </div>

    <div :class="cn('mt-4 flex min-h-0 flex-1 flex-col', collapsed ? 'px-2' : 'px-3')">
      <div v-if="!collapsed" class="px-2.5 pb-1 text-[11px] font-semibold tracking-wider text-muted-foreground">
        最近对话
      </div>
      <div class="min-h-0 flex-1 space-y-0.5 overflow-y-auto pb-2">
        <div
          v-for="s in sessions.sessions"
          :key="s.id"
          class="group relative"
        >
          <RouterLink
            :to="`/c/${s.id}`"
            :title="s.title"
            :class="cn(itemClass(route.params.id === s.id), collapsed ? 'justify-center px-0' : 'pr-8')"
          >
            <span v-if="collapsed" class="text-[12px] font-medium">{{ s.title.trim().slice(0, 1) || '…' }}</span>
            <MessageSquareIcon v-else class="size-3.5 shrink-0 opacity-60" />
            <span v-if="!collapsed" class="truncate">{{ s.title }}</span>
          </RouterLink>
          <button
            v-if="!collapsed"
            class="absolute top-1/2 right-1.5 hidden -translate-y-1/2 rounded-md p-1 text-muted-foreground hover:bg-background hover:text-destructive group-hover:block"
            title="删除对话"
            @click.stop="removeSession(s.id)"
          >
            <Trash2Icon class="size-3.5" />
          </button>
        </div>
        <p v-if="!sessions.sessions.length && !collapsed" class="px-2.5 py-2 text-xs text-muted-foreground">
          还没有对话
        </p>
      </div>
    </div>

    <div v-if="accountOpen" class="fixed inset-0 z-20" @click="toggleAccount" />
    <div :class="cn('relative z-30', collapsed ? 'p-2' : 'p-3')">
      <div
        v-if="accountOpen"
        :class="cn(
          'absolute z-30 mb-2 overflow-hidden rounded-xl border bg-background text-foreground shadow-lg',
          collapsed ? 'bottom-0 left-full ml-2 w-56' : 'inset-x-3 bottom-full',
        )"
      >
        <button
          class="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-[13px] hover:bg-muted/70"
          @click="usageOpen = !usageOpen"
        >
          <MessageSquareIcon class="size-4 text-muted-foreground" />
          <span class="flex-1">使用情况</span>
          <span class="tabular-nums text-muted-foreground">{{ budgetLabel }}</span>
          <ChevronDownIcon :class="cn('size-3.5 text-muted-foreground transition-transform', usageOpen && 'rotate-180')" />
        </button>
        <div v-if="usageOpen" class="space-y-2 border-t px-3 py-2.5 text-[12px] text-muted-foreground">
          <div class="h-1.5 overflow-hidden rounded-full bg-muted">
            <div class="h-full rounded-full bg-foreground" :style="{ width: `${budgetPct}%` }" />
          </div>
          <div class="flex justify-between tabular-nums">
            <span>{{ sessions.usage?.runs ?? 0 }} 次运行</span>
            <span>{{ formatCost(sessions.usage?.cost_cny ?? 0) }}</span>
          </div>
          <div class="flex justify-between tabular-nums">
            <span>
              {{ formatTokens((sessions.usage?.input_tokens ?? 0) + (sessions.usage?.output_tokens ?? 0)) }} tokens
            </span>
            <span>按 ¥{{ DAILY_BUDGET_CNY }} 计</span>
          </div>
          <RouterLink to="/settings/runs" class="inline-block font-medium text-foreground hover:underline" @click="accountOpen = false">
            查看运行记录
          </RouterLink>
        </div>
        <div class="border-t">
          <button
            class="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-[13px] hover:bg-muted/70"
            @click="openSettings"
          >
            <SettingsIcon class="size-4 text-muted-foreground" />
            设置
          </button>
          <button
            class="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-[13px] text-muted-foreground hover:bg-muted/70"
            @click="showHelp"
          >
            <CircleHelpIcon class="size-4" />
            帮助与支持
          </button>
        </div>
      </div>

      <button
        :class="cn(
          'flex w-full items-center gap-2.5 rounded-xl py-1.5 text-left hover:bg-background',
          collapsed ? 'justify-center px-0' : 'px-1.5',
        )"
        :title="collapsed ? agentName : undefined"
        @click="toggleAccount"
      >
        <span class="flex size-8 shrink-0 items-center justify-center rounded-full bg-sky-100 text-[13px] font-semibold text-sky-700">
          {{ agentInitial }}
        </span>
        <span v-if="!collapsed" class="min-w-0 flex-1">
          <span class="block truncate text-[13px] font-semibold leading-5">{{ agentName }}</span>
        </span>
        <ChevronsUpDownIcon v-if="!collapsed" class="size-3.5 shrink-0 text-muted-foreground" />
      </button>

      <p
        v-if="!collapsed && sessions.backendOnline === false"
        class="mt-1 flex items-center gap-1.5 px-1.5 text-[11px] text-destructive"
      >
        <TriangleAlertIcon class="size-3 shrink-0" />
        后端未连接
      </p>
      <p
        v-else-if="!collapsed && sessions.llmConfigured === false"
        class="mt-1 flex items-center gap-1.5 px-1.5 text-[11px] text-amber-700 dark:text-amber-400"
      >
        <TriangleAlertIcon class="size-3 shrink-0" />
        未配置 API Key
      </p>
    </div>
  </aside>
</template>
