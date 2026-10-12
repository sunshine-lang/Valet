<script setup lang="ts">
import {
  CalendarIcon,
  CheckIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ChevronsLeftIcon,
  ChevronsRightIcon,
  ClapperboardIcon,
  FileTextIcon,
  HeartPulseIcon,
  HelpCircleIcon,
  HistoryIcon,
  ImageIcon,
  LanguagesIcon,
  MoonIcon,
  NewspaperIcon,
  PhoneIcon,
  PlusIcon,
  Trash2Icon,
  XIcon,
} from '@lucide/vue'
import { CalendarDate } from '@internationalized/date'
import type { Component } from 'vue'
import { computed, nextTick, onMounted, ref } from 'vue'
import type { DateValue } from 'reka-ui'
import {
  RangeCalendarCell,
  RangeCalendarCellTrigger,
  RangeCalendarGrid,
  RangeCalendarGridBody,
  RangeCalendarGridHead,
  RangeCalendarGridRow,
  RangeCalendarHeadCell,
  RangeCalendarRoot,
} from 'reka-ui'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import PageHeader from '@/components/PageHeader.vue'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { api, ApiError } from '@/lib/api'
import type { ScheduledTask } from '@/lib/types'
import { cn } from '@/lib/utils'

type Repeat = ScheduledTask['repeat']
type Effort = ScheduledTask['effort']

interface Draft {
  name: string
  prompt: string
  effort: Effort
  repeat: Repeat
  intervalHours: number
  hour: number
  minute: number
  second: number
  weekday: number
  weekdays: number[]
  monthDay: number
  month: number
  onceOn: string
  validFrom: string | null
  validUntil: string | null
  notifyWechat: boolean
  enabled: boolean
}

const repeats: { id: Repeat; label: string }[] = [
  { id: 'interval', label: '间隔' },
  { id: 'once', label: '单次' },
  { id: 'daily', label: '每天' },
  { id: 'weekly', label: '每周' },
  { id: 'biweekly', label: '每双周' },
  { id: 'monthly', label: '每月' },
  { id: 'yearly', label: '每年' },
]
const efforts: { id: Effort; label: string }[] = [
  { id: 'off', label: '关闭' },
  { id: 'low', label: '快速' },
  { id: 'medium', label: '中' },
  { id: 'high', label: '高' },
  { id: 'max', label: '极高' },
]
const weekdays = ['一', '二', '三', '四', '五', '六', '日']
const monthNames = ['一月', '二月', '三月', '四月', '五月', '六月', '七月', '八月', '九月', '十月', '十一月', '十二月']
const submenuRepeats = new Set<Repeat>(['weekly', 'biweekly', 'monthly', 'yearly'])

const templates: { icon: Component; name: string; prompt: string; repeat: Repeat; hour: number; minute: number; weekday?: number }[] = [
  { icon: NewspaperIcon, name: '每日 AI 新闻推送', prompt: '关注当天 AI 领域的重要动态，侧重 AI coding。用简体中文整理 5 条，每条写清发生了什么、为什么值得看。', repeat: 'daily', hour: 8, minute: 30 },
  { icon: LanguagesIcon, name: '每日 5 个英语单词', prompt: '每天推荐 5 个高频实用英语单词，包含词义、例句和一句记忆提示。', repeat: 'daily', hour: 8, minute: 0 },
  { icon: MoonIcon, name: '每日儿童睡前故事', prompt: '生成 3–5 分钟可读的温和睡前故事，情节完整，适合小朋友听，不要吓人。', repeat: 'daily', hour: 20, minute: 30 },
  { icon: FileTextIcon, name: '每周工作周报', prompt: '每周五汇总仓库 PR 与 Issue 进展，输出关键变更、风险和需要跟进的事项。', repeat: 'weekly', hour: 17, minute: 0, weekday: 4 },
  { icon: ClapperboardIcon, name: '经典电影推荐', prompt: '推荐一部高分经典电影，简要介绍剧情梗概、亮点和适合什么心情看。不要剧透结局。', repeat: 'weekly', hour: 19, minute: 0, weekday: 5 },
  { icon: HistoryIcon, name: '历史上的今天', prompt: '从科技、电影、音乐等领域挑选一件“今天发生过”的事，讲清楚时间、人物和后来的影响。', repeat: 'daily', hour: 9, minute: 0 },
  { icon: HelpCircleIcon, name: '每日一个为什么', prompt: '每天提出一个有趣问题，先提问再解答，语气轻松，控制在三四段。', repeat: 'daily', hour: 12, minute: 30 },
  { icon: PhoneIcon, name: '父母联系提醒', prompt: '每周日 10:00 提醒你给家人打电话或发消息，给一句可以开口的话。', repeat: 'weekly', hour: 10, minute: 0, weekday: 6 },
  { icon: HeartPulseIcon, name: '体检预约提醒', prompt: '在指定日期提醒你确认体检时间、空腹要求和需要携带的材料。', repeat: 'once', hour: 9, minute: 0 },
  { icon: HelpCircleIcon, name: '面试准备提醒', prompt: '工作日每 2 小时提醒你复习大模型面试内容，每次只问一个问题并给出参考答案。', repeat: 'interval', hour: 9, minute: 0 },
  { icon: CalendarIcon, name: '会议前准备', prompt: '在会议开始前提醒你整理议题、目标、待确认问题和需要提前看的材料。', repeat: 'weekly', hour: 9, minute: 30, weekday: 0 },
  { icon: ImageIcon, name: '可爱萌宠手机壁纸', prompt: '随机从 7 种不同风格中挑选一种，写一段可直接用来生成萌宠手机壁纸的画面描述。', repeat: 'weekly', hour: 18, minute: 0, weekday: 2 },
]

const router = useRouter()
const tasks = ref<ScheduledTask[]>([])
const loading = ref(true)
const saving = ref(false)
const dialogOpen = ref(false)
const editingId = ref<string | null>(null)
const repeatOpen = ref(false)
const submenu = ref<Repeat | null>(null)
const timeOpen = ref(false)
const intervalOpen = ref(false)
const effortOpen = ref(false)
const validOpen = ref(false)
const hourList = ref<HTMLElement>()
const minuteList = ref<HTMLElement>()
const secondList = ref<HTMLElement>()
const timeButton = ref<HTMLElement>()
const intervalButton = ref<HTMLElement>()
const repeatButton = ref<HTMLElement>()
const timeBox = ref({ top: 0, left: 0, width: 220, height: 240 })
const intervalBox = ref({ top: 0, left: 0 })
const repeatBox = ref({ top: 0, left: 0 })
const onceYear = ref(new Date().getFullYear())
const onceMonth = ref(new Date().getMonth() + 1)
const intervalList = ref<HTMLElement>()
const monthList = ref<HTMLElement>()
const yearDayList = ref<HTMLElement>()
const monthDayList = ref<HTMLElement>()
const validButton = ref<HTMLElement>()
const validBox = ref({ top: 0, left: 0, width: 640 })
const placeholder = ref<any>(new CalendarDate(new Date().getFullYear(), new Date().getMonth() + 1, 1))

function isoDate(date: Date) {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

function blankDraft(): Draft {
  const now = new Date()
  const weekday = (now.getDay() + 6) % 7
  return {
    name: '',
    prompt: '',
    effort: 'low',
    repeat: 'daily',
    intervalHours: 1,
    hour: 9,
    minute: 0,
    second: 0,
    weekday,
    weekdays: [weekday],
    monthDay: now.getDate(),
    month: now.getMonth() + 1,
    onceOn: isoDate(now),
    validFrom: null,
    validUntil: null,
    notifyWechat: false,
    enabled: true,
  }
}

const draft = ref<Draft>(blankDraft())

const repeatLabel = computed(() => {
  const names = [...draft.value.weekdays].sort((a, b) => a - b).map((day) => `周${weekdays[day]}`).join('、')
  if (draft.value.repeat === 'weekly') return `每周 ${names}`
  if (draft.value.repeat === 'biweekly') return `双周 ${names}`
  if (draft.value.repeat === 'monthly') return `每月 ${draft.value.monthDay}日`
  if (draft.value.repeat === 'yearly') return `每年 ${draft.value.month}月${draft.value.monthDay}日`
  return repeats.find((item) => item.id === draft.value.repeat)?.label ?? '每天'
})
const effortLabel = computed(() => efforts.find((item) => item.id === draft.value.effort)?.label ?? '快速')
const timeLabel = computed(() => {
  const clock = `${String(draft.value.hour).padStart(2, '0')}:${String(draft.value.minute).padStart(2, '0')}`
  if (draft.value.repeat !== 'once') return clock
  const [year, month, day] = draft.value.onceOn.split('-')
  return `${year}/${Number(month)}/${Number(day)} ${clock}`
})
const validityLabel = computed(() => {
  const { validFrom, validUntil } = draft.value
  if (!validFrom && !validUntil) return '长期有效'
  if (validFrom && validUntil) return `${formatDay(validFrom)} – ${formatDay(validUntil)}`
  return formatDay(validFrom || validUntil || '')
})
function formatDay(value: string) {
  const [year, month, day] = value.split('-')
  return `${year}年${Number(month)}月${Number(day)}日`
}

function toCalendar(value: string | null): DateValue | undefined {
  if (!value) return undefined
  const [year, month, day] = value.split('-').map(Number)
  if (!year || !month || !day) return undefined
  return new CalendarDate(year, month, day)
}

function fromCalendar(value?: { year: number; month: number; day: number } | null) {
  if (!value) return null
  return `${value.year}-${String(value.month).padStart(2, '0')}-${String(value.day).padStart(2, '0')}`
}

const rangeValue = computed<any>({
  get: () => ({
    start: toCalendar(draft.value.validFrom),
    end: toCalendar(draft.value.validUntil),
  }),
  set: (value) => {
    const start = fromCalendar(value?.start)
    const end = fromCalendar(value?.end)
    draft.value.validFrom = start
    draft.value.validUntil = end
    if (start && end) validOpen.value = false
  },
})

function shiftCalendar(months: number) {
  placeholder.value = placeholder.value.add({ months })
}

function weekdayText(days: number[]) {
  return [...days].sort((a, b) => a - b).map((day) => `周${weekdays[day] ?? ''}`).join('、')
}

function scheduleText(task: ScheduledTask) {
  const clock = `${String(task.hour).padStart(2, '0')}:${String(task.minute).padStart(2, '0')}`
  const days = task.weekdays?.length ? task.weekdays : [task.weekday]
  if (task.repeat === 'interval') return `每隔 ${Math.max(1, Math.round(task.interval_minutes / 60))} 小时`
  if (task.repeat === 'once') return `单次 ${task.once_on ? task.once_on.replaceAll('-', '/') : ''} ${clock}`
  if (task.repeat === 'daily') return `每天 ${clock}`
  if (task.repeat === 'weekly') return `每周 ${weekdayText(days)} ${clock}`
  if (task.repeat === 'biweekly') return `双周 ${weekdayText(days)} ${clock}`
  if (task.repeat === 'monthly') return `每月 ${task.month_day}日 ${clock}`
  return `每年 ${task.month}月${task.month_day}日 ${clock}`
}

function formatWhen(value: string | null) {
  if (!value) return '没有下次运行'
  return new Date(value).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function load() {
  loading.value = true
  try {
    tasks.value = await api.listSchedules()
  } catch (error) {
    toast.error(error instanceof ApiError ? error.message : '定时任务加载失败')
  } finally {
    loading.value = false
  }
}

function closePopovers() {
  repeatOpen.value = false
  submenu.value = null
  timeOpen.value = false
  intervalOpen.value = false
  effortOpen.value = false
  validOpen.value = false
}

function openNew(partial?: Partial<Draft>) {
  editingId.value = null
  const next = { ...blankDraft(), ...partial }
  if (partial?.weekday !== undefined && !partial.weekdays) next.weekdays = [partial.weekday]
  draft.value = next
  closePopovers()
  const now = new Date()
  placeholder.value = new CalendarDate(now.getFullYear(), now.getMonth() + 1, 1)
  const [year, month] = next.onceOn.split('-').map(Number)
  onceYear.value = year
  onceMonth.value = month
  dialogOpen.value = true
}

function openTask(task: ScheduledTask) {
  editingId.value = task.id
  draft.value = {
    name: task.name,
    prompt: task.prompt,
    effort: task.effort,
    repeat: task.repeat,
    intervalHours: Math.max(1, Math.round(task.interval_minutes / 60)),
    hour: task.hour,
    minute: task.minute,
    second: task.second ?? 0,
    weekday: task.weekday,
    weekdays: task.weekdays?.length ? [...task.weekdays] : [task.weekday],
    monthDay: task.month_day,
    month: task.month,
    onceOn: task.once_on || isoDate(new Date()),
    validFrom: task.valid_from,
    validUntil: task.valid_until,
    notifyWechat: task.notify_wechat,
    enabled: task.enabled,
  }
  dialogOpen.value = true
}

function payload() {
  return {
    name: draft.value.name.trim(),
    prompt: draft.value.prompt.trim(),
    effort: draft.value.effort,
    repeat: draft.value.repeat,
    interval_minutes: Math.max(1, draft.value.intervalHours) * 60,
    hour: draft.value.hour,
    minute: draft.value.minute,
    second: draft.value.second,
    weekday: draft.value.weekdays[0] ?? draft.value.weekday,
    weekdays: [...draft.value.weekdays].sort((a, b) => a - b),
    month_day: draft.value.monthDay,
    month: draft.value.month,
    once_on: draft.value.repeat === 'once' ? draft.value.onceOn : null,
    valid_from: draft.value.repeat === 'once' ? null : draft.value.validFrom,
    valid_until: draft.value.repeat === 'once' ? null : draft.value.validUntil,
    notify_wechat: false,
    enabled: draft.value.enabled,
  }
}

async function save() {
  closePopovers()
  if (!draft.value.name.trim() || !draft.value.prompt.trim()) {
    toast.error('请填写任务名称和提示词')
    return
  }
  saving.value = true
  try {
    const body = payload()
    if (editingId.value) await api.updateSchedule(editingId.value, body)
    else await api.createSchedule(body)
    dialogOpen.value = false
    await load()
  } catch (error) {
    toast.error(error instanceof ApiError ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}

async function toggleTask(task: ScheduledTask, enabled: boolean) {
  try {
    await api.updateSchedule(task.id, {
      name: task.name,
      prompt: task.prompt,
      effort: task.effort,
      repeat: task.repeat,
      interval_minutes: task.interval_minutes,
      hour: task.hour,
      minute: task.minute,
      second: task.second ?? 0,
      weekday: task.weekday,
      weekdays: task.weekdays?.length ? task.weekdays : [task.weekday],
      month_day: task.month_day,
      month: task.month,
      once_on: task.once_on,
      valid_from: task.valid_from,
      valid_until: task.valid_until,
      notify_wechat: task.notify_wechat,
      enabled,
    })
    await load()
  } catch (error) {
    toast.error(error instanceof ApiError ? error.message : '更新失败')
  }
}

async function removeTask(task: ScheduledTask) {
  try {
    await api.deleteSchedule(task.id)
    await load()
  } catch (error) {
    toast.error(error instanceof ApiError ? error.message : '删除失败')
  }
}

function placeAbove(anchor: HTMLElement | undefined, width: number, height: number) {
  const rect = anchor?.getBoundingClientRect()
  if (!rect) return { top: 8, left: 8 }
  return {
    top: Math.max(8, rect.top - height - 8),
    left: Math.min(Math.max(8, rect.left), window.innerWidth - width - 8),
  }
}

function placeTimePanel() {
  const wide = draft.value.repeat === 'once'
  const width = wide ? Math.min(560, window.innerWidth - 16) : 220
  const height = wide ? 392 : 240
  timeBox.value = { ...placeAbove(timeButton.value, width, height), width, height }
}

function monthCells(year: number, month: number) {
  const first = new Date(year, month - 1, 1)
  const start = new Date(first)
  start.setDate(1 - ((first.getDay() + 6) % 7))
  return Array.from({ length: 6 }, (_, week) =>
    Array.from({ length: 7 }, (_, day) => {
      const date = new Date(start)
      date.setDate(start.getDate() + week * 7 + day)
      return date
    }),
  )
}

function shiftOnce(months: number) {
  const next = new Date(onceYear.value, onceMonth.value - 1 + months, 1)
  onceYear.value = next.getFullYear()
  onceMonth.value = next.getMonth() + 1
}

function pickOnceDay(date: Date) {
  draft.value.onceOn = isoDate(date)
}

function onceCellClass(date: Date, index: number, week: Date[]) {
  const key = isoDate(date)
  const selected = key === draft.value.onceOn
  const before = key < draft.value.onceOn
  const prevBefore = index > 0 && isoDate(week[index - 1]) < draft.value.onceOn
  const nextBefore = index < 6 && isoDate(week[index + 1]) < draft.value.onceOn
  const inMonth = date.getMonth() + 1 === onceMonth.value
  return cn(
    'h-8 flex-1 text-[13px]',
    !inMonth && !selected && 'text-slate-400',
    before && 'bg-[#d7ebff]',
    before && !prevBefore && 'rounded-l-md',
    before && !nextBefore && 'rounded-r-md',
    selected && 'relative z-10 rounded-md bg-sky-500 font-medium text-white',
  )
}

function toggleWeekday(index: number) {
  const selected = new Set(draft.value.weekdays)
  if (selected.has(index)) {
    if (selected.size === 1) return
    selected.delete(index)
  } else {
    selected.add(index)
  }
  draft.value.weekdays = [...selected].sort((a, b) => a - b)
  draft.value.weekday = draft.value.weekdays[0]
}

function focusSubmenu() {
  nextTick(() => {
    centerColumn(monthDayList.value)
    centerColumn(monthList.value)
    centerColumn(yearDayList.value)
  })
}

function previewRepeat(id: Repeat) {
  if (!submenuRepeats.has(id)) {
    submenu.value = null
    return
  }
  submenu.value = id
  draft.value.repeat = id
  focusSubmenu()
}

function chooseRepeat(id: Repeat) {
  if (id === 'once' && draft.value.repeat !== 'once') {
    const now = new Date()
    draft.value.onceOn = isoDate(now)
    draft.value.hour = now.getHours()
    draft.value.minute = now.getMinutes()
    draft.value.second = now.getSeconds()
    onceYear.value = now.getFullYear()
    onceMonth.value = now.getMonth() + 1
  }
  draft.value.repeat = id
  if (submenuRepeats.has(id)) {
    submenu.value = id
    repeatOpen.value = true
    focusSubmenu()
    return
  }
  submenu.value = null
  repeatOpen.value = false
}

function toggleRepeat() {
  timeOpen.value = false
  intervalOpen.value = false
  validOpen.value = false
  effortOpen.value = false
  repeatOpen.value = !repeatOpen.value
  if (!repeatOpen.value) {
    submenu.value = null
    return
  }
  submenu.value = submenuRepeats.has(draft.value.repeat) ? draft.value.repeat : null
  const rect = repeatButton.value?.getBoundingClientRect()
  if (!rect) return
  repeatBox.value = { top: rect.top - 8, left: rect.left }
  nextTick(() => {
    centerColumn(monthDayList.value)
    centerColumn(monthList.value)
    centerColumn(yearDayList.value)
  })
}

function centerColumn(list: HTMLElement | undefined) {
  const selected = list?.querySelector('[data-selected]') as HTMLElement | null
  if (!list || !selected) return
  list.scrollTop = selected.offsetTop - list.clientHeight / 2 + selected.clientHeight / 2
}

function toggleValid() {
  validOpen.value = !validOpen.value
  repeatOpen.value = false
  timeOpen.value = false
  if (!validOpen.value) return
  const rect = validButton.value?.getBoundingClientRect()
  if (!rect) return
  const width = Math.min(640, window.innerWidth - 16)
  const left = Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8))
  validBox.value = { top: Math.max(8, rect.top - 360 - 8), left, width }
}

function toggleInterval() {
  const next = !intervalOpen.value
  closePopovers()
  intervalOpen.value = next
  if (!next) return
  intervalBox.value = placeAbove(intervalButton.value, 160, 240)
  nextTick(() => centerColumn(intervalList.value))
}

function toggleTime() {
  repeatOpen.value = false
  submenu.value = null
  intervalOpen.value = false
  validOpen.value = false
  timeOpen.value = !timeOpen.value
  if (!timeOpen.value) return
  if (draft.value.repeat === 'once') {
    const [year, month] = draft.value.onceOn.split('-').map(Number)
    onceYear.value = year
    onceMonth.value = month
  }
  placeTimePanel()
  nextTick(() => {
    nextTick(() => {
      centerColumn(hourList.value)
      centerColumn(minuteList.value)
      centerColumn(secondList.value)
    })
  })
}

onMounted(load)
</script>

<template>
  <PageHeader title="定时任务">
    <template #actions>
      <Button class="rounded-lg" @click="openNew()">
        <PlusIcon />
        新建
      </Button>
    </template>
  </PageHeader>

  <div class="min-h-0 flex-1 overflow-y-auto bg-sky-50/40 px-6 py-8 dark:bg-background">
    <div v-if="loading" class="py-24 text-center text-sm text-muted-foreground">加载中…</div>
    <template v-else-if="tasks.length">
      <div class="mx-auto grid max-w-5xl gap-3">
        <article
          v-for="task in tasks"
          :key="task.id"
          class="flex items-center gap-4 rounded-2xl border bg-background px-4 py-3"
        >
          <button type="button" class="min-w-0 flex-1 text-left" @click="openTask(task)">
            <div class="truncate text-[15px] font-medium">{{ task.name }}</div>
            <div class="mt-1 text-[13px] text-muted-foreground">
              {{ scheduleText(task) }}
              <span v-if="task.valid_from || task.valid_until"> · {{ task.valid_from || '…' }} 至 {{ task.valid_until || '长期' }}</span>
            </div>
            <div class="mt-1 text-[12px] text-muted-foreground">下次 {{ formatWhen(task.next_run_at) }}</div>
          </button>
          <button
            v-if="task.last_session_id"
            type="button"
            class="text-[13px] text-sky-700 hover:underline"
            @click="router.push(`/c/${task.last_session_id}`)"
          >
            查看对话
          </button>
          <Switch :checked="task.enabled" @update:checked="toggleTask(task, $event)" />
          <button type="button" class="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground" title="删除" @click="removeTask(task)">
            <Trash2Icon class="size-4" />
          </button>
        </article>
      </div>
    </template>
    <template v-else>
      <div class="flex flex-col items-center pt-16 pb-10 text-muted-foreground">
        <div class="flex size-16 items-center justify-center rounded-full bg-white text-slate-300 shadow-sm dark:bg-muted">
          <svg viewBox="0 0 64 64" class="size-10" aria-hidden="true">
            <circle cx="32" cy="28" r="14" fill="none" stroke="currentColor" stroke-width="2" />
            <circle cx="26" cy="26" r="2" fill="currentColor" />
            <circle cx="38" cy="26" r="2" fill="currentColor" />
            <path d="M27 33c1.5 2 8.5 2 10 0" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
            <path d="M32 14v-4M22 18l-3-3M42 18l3-3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
            <rect x="24" y="42" width="16" height="8" rx="3" fill="none" stroke="currentColor" stroke-width="2" />
          </svg>
        </div>
        <p class="mt-4 text-[14px]">暂无定时任务</p>
      </div>
      <div class="mx-auto max-w-5xl">
        <h2 class="mb-3 text-[13px] text-muted-foreground">试试这些常用任务</h2>
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <button
            v-for="item in templates"
            :key="item.name"
            type="button"
            class="rounded-2xl border bg-background px-4 py-3 text-left hover:border-sky-200"
            @click="openNew({ name: item.name, prompt: item.prompt, repeat: item.repeat, hour: item.hour, minute: item.minute, weekday: item.weekday ?? draft.weekday })"
          >
            <div class="flex items-center gap-2 text-[14px] font-medium">
              <component :is="item.icon" class="size-4 text-muted-foreground" />
              {{ item.name }}
            </div>
            <p class="mt-1 line-clamp-2 text-[12px] leading-5 text-muted-foreground">{{ item.prompt }}</p>
          </button>
        </div>
      </div>
    </template>
  </div>

  <div v-if="dialogOpen" class="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-6" @click.self="dialogOpen = false">
    <div class="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border bg-background shadow-xl">
      <div class="flex items-center justify-between px-5 py-4">
        <h2 class="text-[16px] font-semibold">{{ editingId ? '编辑定时任务' : '新建定时任务' }}</h2>
        <button type="button" class="rounded-md p-1 text-muted-foreground hover:bg-muted" @click="dialogOpen = false">
          <XIcon class="size-4" />
        </button>
      </div>
      <div class="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 pt-1 pb-5">
        <input
          v-model="draft.name"
          placeholder="输入任务名称"
          class="h-11 w-full rounded-lg border border-input bg-background px-3 text-[14px] outline-none focus:border-sky-400 focus:ring-1 focus:ring-sky-300"
        />
        <div class="rounded-2xl border border-sky-100 px-3 py-3">
          <textarea
            v-model="draft.prompt"
            rows="5"
            placeholder="添加提示词"
            class="w-full resize-none bg-transparent text-[14px] leading-6 outline-none"
          />
          <div class="relative mt-2 flex justify-end">
            <button type="button" class="inline-flex items-center gap-1 text-[13px] text-muted-foreground" @click="effortOpen = !effortOpen">
              {{ effortLabel }}
              <ChevronDownIcon class="size-3.5" />
            </button>
            <div v-if="effortOpen" class="absolute right-0 bottom-full z-10 mb-1 w-28 rounded-xl border bg-popover py-1 shadow-lg">
              <button
                v-for="item in efforts"
                :key="item.id"
                type="button"
                class="flex w-full items-center px-3 py-2 text-left text-[13px] hover:bg-muted/70"
                @click="draft.effort = item.id; effortOpen = false"
              >
                <span class="flex-1">{{ item.label }}</span>
                <CheckIcon v-if="item.id === draft.effort" class="size-3.5" />
              </button>
            </div>
          </div>
        </div>

        <div class="grid grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)_minmax(0,1fr)] gap-3">
          <div>
            <button
              ref="repeatButton"
              type="button"
              class="flex h-11 w-full items-center justify-between gap-2 rounded-lg border px-3 text-[13px]"
              @click="toggleRepeat"
            >
              <span class="truncate">重复：{{ repeatLabel }}</span>
              <ChevronDownIcon :class="cn('size-4 shrink-0 text-muted-foreground', repeatOpen && 'rotate-180')" />
            </button>
          </div>
          <div :class="draft.repeat === 'once' && 'col-span-2'">
            <button
              v-if="draft.repeat === 'interval'"
              ref="intervalButton"
              type="button"
              class="flex h-11 w-full items-center justify-between rounded-lg border px-3 text-[14px]"
              @click="toggleInterval"
            >
              每隔：{{ draft.intervalHours }} 小时
              <ChevronDownIcon :class="cn('size-4 text-muted-foreground', intervalOpen && 'rotate-180')" />
            </button>
            <button
              v-else
              ref="timeButton"
              type="button"
              class="flex h-11 w-full items-center justify-between rounded-lg border px-3 text-[14px]"
              @click="toggleTime"
            >
              <span class="truncate">时间：{{ timeLabel }}</span>
              <ChevronDownIcon :class="cn('size-4 shrink-0 text-muted-foreground', timeOpen && 'rotate-180')" />
            </button>
          </div>
          <div v-if="draft.repeat !== 'once'">
            <button
              ref="validButton"
              type="button"
              class="flex h-11 w-full items-center justify-between rounded-lg border px-3 text-[14px]"
              @click="toggleValid"
            >
              <span class="truncate">有效期：{{ validityLabel }}</span>
              <ChevronDownIcon :class="cn('size-4 shrink-0 text-muted-foreground', validOpen && 'rotate-180')" />
            </button>
          </div>
        </div>

      </div>
      <div class="flex shrink-0 justify-end gap-2 border-t px-5 py-4">
        <Button variant="outline" class="rounded-lg" @click="dialogOpen = false">取消</Button>
        <Button class="rounded-lg" :disabled="saving" @click="save">确定</Button>
      </div>
    </div>
  </div>
  <Teleport to="body">
    <div
      v-if="dialogOpen && repeatOpen"
      class="fixed z-50 flex -translate-y-full items-start"
      :style="{ top: `${repeatBox.top}px`, left: `${repeatBox.left}px` }"
    >
      <div class="w-36 rounded-xl border bg-popover py-1 shadow-lg">
        <button
          v-for="item in repeats"
          :key="item.id"
          type="button"
          :class="cn('flex w-full items-center px-3 py-2 text-left text-[14px]', (submenu === item.id || (!submenu && draft.repeat === item.id)) ? 'bg-sky-100' : 'hover:bg-muted/70')"
          @mouseenter="previewRepeat(item.id)"
          @click="chooseRepeat(item.id)"
        >
          <span class="flex-1">{{ item.label }}</span>
          <ChevronRightIcon v-if="submenuRepeats.has(item.id)" class="size-3.5 text-muted-foreground" />
        </button>
      </div>
      <div v-if="submenu === 'weekly' || submenu === 'biweekly'" class="ml-1 w-36 rounded-xl border bg-popover py-1 shadow-lg">
        <button
          v-for="(label, index) in weekdays"
          :key="label"
          type="button"
          :class="cn('flex w-full items-center px-3 py-2 text-left text-[14px]', draft.weekdays.includes(index) ? 'bg-sky-50' : 'hover:bg-muted/70')"
          @click="toggleWeekday(index)"
        >
          <span class="flex-1">周{{ label }}</span>
          <CheckIcon v-if="draft.weekdays.includes(index)" class="size-3.5 text-sky-600" />
        </button>
      </div>
      <div v-else-if="submenu === 'monthly'" ref="monthDayList" class="time-scroll ml-1 h-64 w-32 overflow-y-auto rounded-xl border bg-popover py-1 shadow-lg" @wheel.stop>
        <button
          v-for="day in 31"
          :key="day"
          type="button"
          :data-selected="draft.monthDay === day || undefined"
          :class="cn('flex w-[calc(100%-8px)] items-center rounded-lg px-3 py-2 text-left text-[14px]', draft.monthDay === day ? 'bg-sky-100' : 'hover:bg-muted/70')"
          style="margin: 0 4px"
          @click="draft.monthDay = day"
        >
          <span class="flex-1">{{ day }}日</span>
          <CheckIcon v-if="draft.monthDay === day" class="size-3.5 text-sky-600" />
        </button>
      </div>
      <div v-else-if="submenu === 'yearly'" class="ml-1 flex h-64 overflow-hidden rounded-xl border bg-popover shadow-lg">
        <div ref="monthList" class="time-scroll h-full w-28 overflow-y-auto py-1" @wheel.stop>
          <button
            v-for="(label, index) in monthNames"
            :key="label"
            type="button"
            :data-selected="draft.month === index + 1 || undefined"
            :class="cn('mx-1 flex h-9 w-[calc(100%-8px)] items-center rounded-lg px-3 text-[14px]', draft.month === index + 1 ? 'bg-sky-100' : 'hover:bg-muted/70')"
            @click="draft.month = index + 1"
          >
            {{ label }}
          </button>
        </div>
        <div ref="yearDayList" class="time-scroll h-full w-16 overflow-y-auto border-l py-1" @wheel.stop>
          <button
            v-for="day in 31"
            :key="day"
            type="button"
            :data-selected="draft.monthDay === day || undefined"
            :class="cn('mx-1 flex h-9 w-[calc(100%-8px)] items-center justify-center rounded-lg text-[14px] tabular-nums', draft.monthDay === day ? 'bg-sky-100' : 'hover:bg-muted/70')"
            @click="draft.monthDay = day"
          >
            {{ String(day).padStart(2, '0') }}
          </button>
        </div>
      </div>
    </div>
    <div
      v-if="dialogOpen && intervalOpen"
      ref="intervalList"
      class="time-scroll fixed z-50 h-60 w-40 overflow-y-auto rounded-xl border bg-popover py-1 shadow-lg"
      :style="{ top: `${intervalBox.top}px`, left: `${intervalBox.left}px` }"
      @wheel.stop
    >
      <button
        v-for="hour in 24"
        :key="hour"
        type="button"
        :data-selected="draft.intervalHours === hour || undefined"
        :class="cn('mx-1 flex h-9 w-[calc(100%-8px)] items-center rounded-lg px-3 text-[14px]', draft.intervalHours === hour ? 'bg-sky-100' : 'hover:bg-muted/70')"
        @click="draft.intervalHours = hour"
      >
        {{ hour }} 小时
      </button>
    </div>
    <div
      v-if="dialogOpen && timeOpen && draft.repeat === 'once'"
      class="fixed z-50 overflow-hidden rounded-xl border bg-popover shadow-lg"
      :style="{ top: `${timeBox.top}px`, left: `${timeBox.left}px`, width: `${timeBox.width}px` }"
    >
      <div class="flex">
        <div class="w-[300px] shrink-0 p-3">
          <div class="mb-2 flex items-center justify-between text-[14px] font-medium">
            <div class="flex">
              <button type="button" class="rounded p-1 hover:bg-muted" @click="shiftOnce(-12)"><ChevronsLeftIcon class="size-4" /></button>
              <button type="button" class="rounded p-1 hover:bg-muted" @click="shiftOnce(-1)"><ChevronLeftIcon class="size-4" /></button>
            </div>
            {{ onceYear }}年 {{ onceMonth }}月
            <div class="flex">
              <button type="button" class="rounded p-1 hover:bg-muted" @click="shiftOnce(1)"><ChevronRightIcon class="size-4" /></button>
              <button type="button" class="rounded p-1 hover:bg-muted" @click="shiftOnce(12)"><ChevronsRightIcon class="size-4" /></button>
            </div>
          </div>
          <div class="mb-1 flex text-center text-[12px] text-muted-foreground">
            <span v-for="label in weekdays" :key="label" class="h-8 flex-1 leading-8">{{ label }}</span>
          </div>
          <div v-for="(week, weekIndex) in monthCells(onceYear, onceMonth)" :key="weekIndex" class="flex">
            <button
              v-for="(date, index) in week"
              :key="isoDate(date)"
              type="button"
              :class="onceCellClass(date, index, week)"
              @click="pickOnceDay(date)"
            >
              {{ date.getDate() }}
            </button>
          </div>
        </div>
        <div class="flex h-[300px] min-w-0 flex-1 border-l">
          <div ref="hourList" class="time-scroll h-full min-w-0 flex-1 overflow-y-auto py-1" @wheel.stop>
            <button v-for="hour in 24" :key="hour" type="button" :data-selected="draft.hour === hour - 1 || undefined" :class="cn('mx-1 flex h-9 items-center justify-center rounded-lg text-[14px] tabular-nums', draft.hour === hour - 1 ? 'bg-sky-100 text-sky-950' : 'hover:bg-muted/70')" style="width: calc(100% - 8px)" @click="draft.hour = hour - 1">{{ String(hour - 1).padStart(2, '0') }}</button>
          </div>
          <div ref="minuteList" class="time-scroll h-full min-w-0 flex-1 overflow-y-auto border-l py-1" @wheel.stop>
            <button v-for="minute in 60" :key="minute" type="button" :data-selected="draft.minute === minute - 1 || undefined" :class="cn('mx-1 flex h-9 items-center justify-center rounded-lg text-[14px] tabular-nums', draft.minute === minute - 1 ? 'bg-sky-100 text-sky-950' : 'hover:bg-muted/70')" style="width: calc(100% - 8px)" @click="draft.minute = minute - 1">{{ String(minute - 1).padStart(2, '0') }}</button>
          </div>
          <div ref="secondList" class="time-scroll h-full min-w-0 flex-1 overflow-y-auto border-l py-1" @wheel.stop>
            <button v-for="second in 60" :key="second" type="button" :data-selected="draft.second === second - 1 || undefined" :class="cn('mx-1 flex h-9 items-center justify-center rounded-lg text-[14px] tabular-nums', draft.second === second - 1 ? 'bg-sky-100 text-sky-950' : 'hover:bg-muted/70')" style="width: calc(100% - 8px)" @click="draft.second = second - 1">{{ String(second - 1).padStart(2, '0') }}</button>
          </div>
        </div>
      </div>
      <div class="flex justify-end px-3 pt-1 pb-3">
        <button type="button" class="rounded-lg bg-sky-500 px-5 py-1.5 text-[14px] text-white hover:bg-sky-600" @click="timeOpen = false">确认</button>
      </div>
    </div>
    <div
      v-else-if="dialogOpen && timeOpen"
      class="fixed z-50 flex overflow-hidden rounded-xl border bg-popover shadow-lg"
      :style="{ top: `${timeBox.top}px`, left: `${timeBox.left}px`, width: `${timeBox.width}px`, height: `${timeBox.height}px` }"
    >
      <div
        ref="hourList"
        class="time-scroll overflow-y-auto overscroll-contain py-1"
        style="height: 100%; width: 50%; min-width: 0"
        @wheel.stop
      >
        <button
          v-for="hour in 24"
          :key="hour"
          type="button"
          :data-selected="draft.hour === hour - 1 || undefined"
          :class="cn('flex h-9 items-center justify-center rounded-lg text-[14px] tabular-nums', draft.hour === hour - 1 ? 'bg-sky-100 text-sky-950' : 'hover:bg-muted/70')"
          style="width: calc(100% - 8px); margin: 0 4px"
          @click="draft.hour = hour - 1"
        >
          {{ String(hour - 1).padStart(2, '0') }}
        </button>
      </div>
      <div
        ref="minuteList"
        class="time-scroll overflow-y-auto overscroll-contain border-l py-1"
        style="height: 100%; width: 50%; min-width: 0"
        @wheel.stop
      >
        <button
          v-for="minute in 60"
          :key="minute"
          type="button"
          :data-selected="draft.minute === minute - 1 || undefined"
          :class="cn('flex h-9 items-center justify-center rounded-lg text-[14px] tabular-nums', draft.minute === minute - 1 ? 'bg-sky-100 text-sky-950' : 'hover:bg-muted/70')"
          style="width: calc(100% - 8px); margin: 0 4px"
          @click="draft.minute = minute - 1"
        >
          {{ String(minute - 1).padStart(2, '0') }}
        </button>
      </div>
    </div>
    <div
      v-if="dialogOpen && validOpen"
      class="validity-cal fixed z-50 rounded-2xl border bg-popover p-4 shadow-lg"
      :style="{ top: `${validBox.top}px`, left: `${validBox.left}px`, width: `${validBox.width}px` }"
    >
      <div class="mb-2 flex justify-end">
        <button type="button" class="text-[13px] text-sky-700" @click="draft.validFrom = null; draft.validUntil = null; validOpen = false">长期有效</button>
      </div>
      <RangeCalendarRoot
        v-model="rangeValue"
        v-model:placeholder="placeholder"
        locale="zh-CN"
        :number-of-months="2"
        :week-starts-on="1"
        weekday-format="narrow"
        fixed-weeks
      >
        <template #default="{ grid, weekDays }">
          <div class="grid grid-cols-2 gap-6">
            <div v-for="month in grid" :key="month.value.toString()">
              <div class="mb-2 flex items-center justify-between text-[14px] font-medium">
                <div class="flex">
                  <button type="button" class="rounded p-1 hover:bg-muted" @click="shiftCalendar(-12)"><ChevronsLeftIcon class="size-4" /></button>
                  <button type="button" class="rounded p-1 hover:bg-muted" @click="shiftCalendar(-1)"><ChevronLeftIcon class="size-4" /></button>
                </div>
                {{ month.value.year }}年 {{ month.value.month }}月
                <div class="flex">
                  <button type="button" class="rounded p-1 hover:bg-muted" @click="shiftCalendar(1)"><ChevronRightIcon class="size-4" /></button>
                  <button type="button" class="rounded p-1 hover:bg-muted" @click="shiftCalendar(12)"><ChevronsRightIcon class="size-4" /></button>
                </div>
              </div>
              <RangeCalendarGrid as="div" class="w-full">
                <RangeCalendarGridHead as="div">
                  <RangeCalendarGridRow as="div" class="flex">
                    <RangeCalendarHeadCell v-for="day in weekDays" :key="day" as="div" class="h-8 flex-1 text-center text-[12px] leading-8 font-normal text-muted-foreground">
                      {{ String(day).replace('周', '') }}
                    </RangeCalendarHeadCell>
                  </RangeCalendarGridRow>
                </RangeCalendarGridHead>
                <RangeCalendarGridBody as="div">
                  <RangeCalendarGridRow v-for="(weekDates, index) in month.rows" :key="index" as="div" class="cal-row mt-0.5 flex">
                    <RangeCalendarCell
                      v-for="weekDate in weekDates"
                      :key="weekDate.toString()"
                      :date="weekDate"
                      as="div"
                      class="relative flex-1"
                    >
                      <RangeCalendarCellTrigger
                        :day="weekDate"
                        :month="month.value"
                        class="relative z-10 flex h-8 w-full items-center justify-center text-[13px] outline-none"
                      />
                    </RangeCalendarCell>
                  </RangeCalendarGridRow>
                </RangeCalendarGridBody>
              </RangeCalendarGrid>
            </div>
          </div>
        </template>
      </RangeCalendarRoot>
    </div>
  </Teleport>
</template>

<style scoped>
.time-scroll {
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.22) transparent;
}
.time-scroll::-webkit-scrollbar {
  width: 2px;
}
.time-scroll::-webkit-scrollbar-track {
  background: transparent;
}
.time-scroll::-webkit-scrollbar-thumb {
  background-color: rgba(148, 163, 184, 0.22);
  border-radius: 999px;
}
.validity-cal :deep([data-selected]),
.validity-cal :deep([data-highlighted]) {
  background: #d7ebff;
}
.validity-cal :deep(.cal-row > :first-child [data-selected]),
.validity-cal :deep(.cal-row > :first-child [data-highlighted]),
.validity-cal :deep([data-selection-start]),
.validity-cal :deep([data-highlighted-start]) {
  border-top-left-radius: 6px;
  border-bottom-left-radius: 6px;
}
.validity-cal :deep(.cal-row > :last-child [data-selected]),
.validity-cal :deep(.cal-row > :last-child [data-highlighted]),
.validity-cal :deep([data-selection-end]),
.validity-cal :deep([data-highlighted-end]) {
  border-top-right-radius: 6px;
  border-bottom-right-radius: 6px;
}
.validity-cal :deep([data-today])::after {
  content: '';
  position: absolute;
  inset: 2px;
  border: 1.5px solid #334155;
  border-radius: 6px;
  pointer-events: none;
}
.validity-cal :deep([data-outside-view]) {
  color: rgb(100 116 139 / 0.55);
}
</style>
