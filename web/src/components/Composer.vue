<script setup lang="ts">
import { ArrowUpIcon, CheckIcon, ChevronRightIcon, HammerIcon, HandIcon, PaperclipIcon, PinIcon, PlusIcon, SearchIcon, SettingsIcon, ShieldCheckIcon, SparklesIcon, SquareIcon, TriangleAlertIcon, UploadIcon, XIcon } from '@lucide/vue'
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import ContextMeter from '@/components/ContextMeter.vue'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface CatalogSkill {
  name: string
  title: string
  description: string
}

const props = withDefaults(
  defineProps<{
    busy?: boolean
    disabled?: boolean
    hero?: boolean
    placeholder?: string
    model?: string
    models?: { id: string; label: string }[]
    effort?: string
    permission?: 'ask' | 'assist' | 'full'
    allowImages?: boolean
    previewText?: string
    skills?: CatalogSkill[]
    context?: {
      limit: number
      system: number
      tools: number
      messages: number
      connectors: number
      skills: number
    }
  }>(),
  {
    busy: false,
    disabled: false,
    hero: false,
    placeholder: '发消息…',
    model: '',
    models: () => [],
    effort: 'high',
    permission: 'assist',
    allowImages: false,
    previewText: '',
    skills: () => [],
    context: () => ({ limit: 131_072, system: 0, tools: 0, messages: 0, connectors: 0, skills: 0 }),
  },
)
const emit = defineEmits<{
  submit: [text: string, files: File[], skills: string[]]
  stop: []
  'update:model': [model: string]
  'update:effort': [effort: string]
  'update:permission': [mode: 'ask' | 'assist' | 'full']
}>()

const MAX_FILES = 4
const MAX_BYTES = 8 * 1024 * 1024

interface PendingFile {
  key: string
  file: File
  preview?: string
}

const router = useRouter()
const pending = ref<PendingFile[]>([])
const selectedSkills = ref<CatalogSkill[]>([])
const fileInput = ref<HTMLInputElement>()
const skillSearch = ref<HTMLInputElement>()
const dragging = ref(false)
const attachOpen = ref(false)
const attachPage = ref<'files' | 'skills'>('files')
const skillQuery = ref('')

const skillTints = [
  'bg-sky-100 text-sky-700',
  'bg-emerald-100 text-emerald-700',
  'bg-violet-100 text-violet-700',
  'bg-amber-100 text-amber-800',
  'bg-rose-100 text-rose-700',
]

function skillTint(name: string) {
  let total = 0
  for (const char of name) total += char.charCodeAt(0)
  return skillTints[total % skillTints.length]
}

function skillInitial(skill: CatalogSkill) {
  return (skill.title.trim() || skill.name).slice(0, 1).toUpperCase()
}

const efforts = [
  { id: 'off', label: '关闭' },
  { id: 'low', label: '低' },
  { id: 'medium', label: '中' },
  { id: 'high', label: '高' },
  { id: 'max', label: '极高' },
]

const permissionOpen = ref(false)
const permissions = [
  {
    id: 'ask' as const,
    label: '请求批准',
    detail: '编辑外部文件和使用互联网时始终询问',
    icon: HandIcon,
  },
  {
    id: 'assist' as const,
    label: '帮我批准',
    detail: '仅对检测到的风险操作请求批准',
    icon: ShieldCheckIcon,
  },
  {
    id: 'full' as const,
    label: '完全访问权限',
    detail: '可不受限制地访问互联网和项目外的文件',
    icon: TriangleAlertIcon,
  },
]
const permissionLabel = computed(() => permissions.find((item) => item.id === props.permission)?.label ?? '帮我批准')
const permissionIcon = computed(() => permissions.find((item) => item.id === props.permission)?.icon ?? ShieldCheckIcon)

const menuOpen = ref(false)
const menuPage = ref<'main' | 'model' | 'effort'>('main')
const contextOpen = ref(false)

const contextParts = computed(() => {
  const base = props.context
  const selected = selectedSkills.value.reduce(
    (sum, skill) => sum + Math.ceil(`${skill.title}\n${skill.description}`.length / 2),
    0,
  )
  return [
    { key: 'system', label: '系统提示词', tokens: base.system, dot: 'bg-blue-500', bar: 'bg-blue-500' },
    { key: 'tools', label: '工具及子智能体', tokens: base.tools, dot: 'bg-emerald-500', bar: 'bg-emerald-500' },
    { key: 'messages', label: '对话消息', tokens: base.messages, dot: 'bg-orange-400', bar: 'bg-orange-400' },
    { key: 'connectors', label: '连接器及MCP', tokens: base.connectors, dot: 'bg-violet-500', bar: 'bg-violet-500' },
    { key: 'skills', label: '技能', tokens: base.skills + selected, dot: 'bg-pink-500', bar: 'bg-pink-500' },
  ]
})

const modelLabel = computed(
  () => modelOptions.value.find((item) => item.id === props.model)?.label || props.model || '选择模型',
)
const effortLabel = computed(() => efforts.find((item) => item.id === props.effort)?.label ?? '高')

function toggleMenu() {
  menuOpen.value = !menuOpen.value
  menuPage.value = 'main'
  if (menuOpen.value) {
    closeAttach()
    contextOpen.value = false
  }
}

function closeAttach() {
  attachOpen.value = false
  attachPage.value = 'files'
  skillQuery.value = ''
}

function toggleAttach() {
  attachOpen.value = !attachOpen.value
  if (attachOpen.value) {
    menuOpen.value = false
    contextOpen.value = false
    permissionOpen.value = false
  } else closeAttach()
}

const attachSkills = computed(() => {
  const needle = skillQuery.value.trim().toLowerCase()
  if (!needle) return props.skills
  return props.skills.filter((skill) =>
    [skill.name, skill.title, skill.description].some((item) => item.toLowerCase().includes(needle)),
  )
})

function chooseSkill(skill: CatalogSkill) {
  if (!selectedSkills.value.some((item) => item.name === skill.name)) {
    selectedSkills.value = [...selectedSkills.value, skill]
  }
  closeAttach()
  nextTick(resize)
}

function openSkillLibrary(importZip = false) {
  closeAttach()
  router.push(importZip ? { path: '/skills', query: { import: '1' } } : '/skills')
}

watch(attachPage, (page) => {
  if (page === 'skills') nextTick(() => skillSearch.value?.focus())
})

function pickFiles() {
  closeAttach()
  fileInput.value?.click()
}

function toggleSkill(skill: CatalogSkill) {
  const exists = selectedSkills.value.some((item) => item.name === skill.name)
  selectedSkills.value = exists
    ? selectedSkills.value.filter((item) => item.name !== skill.name)
    : [...selectedSkills.value, skill]
}

function chooseModel(id: string) {
  emit('update:model', id)
}

function chooseEffort(id: string) {
  emit('update:effort', id)
}

const modelOptions = computed(() => {
  const options = props.models.map((item) => ({ id: item.id, label: item.label }))
  if (props.model && !options.some((item) => item.id === props.model)) {
    options.unshift({ id: props.model, label: props.model })
  }
  return options
})

const text = defineModel<string>({ default: '' })
const textarea = ref<HTMLTextAreaElement>()
const slashIndex = ref(0)

const slashQuery = computed(() => {
  const match = text.value.match(/^\/(\S*)$/)
  return match ? match[1] : null
})

const slashMatches = computed(() => {
  const query = slashQuery.value
  if (query === null) return []
  const needle = query.toLowerCase()
  return props.skills.filter((skill) =>
    [skill.name, skill.title, skill.description].some((item) => item.toLowerCase().includes(needle)),
  )
})

function activateSkill(skill: CatalogSkill) {
  if (!selectedSkills.value.some((item) => item.name === skill.name)) {
    selectedSkills.value = [...selectedSkills.value, skill]
  }
  text.value = ''
  slashIndex.value = 0
  nextTick(resize)
}

function addFiles(list: File[]) {
  for (const file of list) {
    if (pending.value.length >= MAX_FILES) {
      toast.error(`一次最多 ${MAX_FILES} 个文件`)
      break
    }
    if (file.size > MAX_BYTES) {
      toast.error(`${file.name} 超过 8 MB`)
      continue
    }
    if (file.type.startsWith('image/') && !props.allowImages) {
      toast.error('当前模型不支持图片')
      continue
    }
    pending.value.push({
      key: crypto.randomUUID(),
      file,
      preview: file.type.startsWith('image/') ? URL.createObjectURL(file) : undefined,
    })
  }
}

function removeFile(key: string) {
  const item = pending.value.find((file) => file.key === key)
  if (item?.preview) URL.revokeObjectURL(item.preview)
  pending.value = pending.value.filter((file) => file.key !== key)
}

function onPick(event: Event) {
  const input = event.target as HTMLInputElement
  addFiles([...(input.files ?? [])])
  input.value = ''
}

function onPaste(event: ClipboardEvent) {
  const files = [...(event.clipboardData?.files ?? [])]
  if (!files.length) return
  event.preventDefault()
  addFiles(files)
}

function onDrop(event: DragEvent) {
  dragging.value = false
  const files = [...(event.dataTransfer?.files ?? [])]
  if (!files.length) return
  event.preventDefault()
  addFiles(files)
}

function submit() {
  const typed = text.value.trim()
  const skills = selectedSkills.value.map((skill) => skill.name)
  if ((!typed && !pending.value.length && !skills.length) || props.disabled) return
  const files = pending.value.map((item) => item.file)
  for (const item of pending.value) if (item.preview) URL.revokeObjectURL(item.preview)
  pending.value = []
  selectedSkills.value = []
  closeAttach()
  emit('submit', typed, files, skills)
  text.value = ''
  nextTick(resize)
}

watch(slashQuery, () => {
  slashIndex.value = 0
})

function onKeydown(e: KeyboardEvent) {
  if (slashQuery.value !== null) {
    if (slashMatches.value.length && e.key === 'ArrowDown') {
      e.preventDefault()
      slashIndex.value = (slashIndex.value + 1) % slashMatches.value.length
      return
    }
    if (slashMatches.value.length && e.key === 'ArrowUp') {
      e.preventDefault()
      slashIndex.value = (slashIndex.value - 1 + slashMatches.value.length) % slashMatches.value.length
      return
    }
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault()
      const skill = slashMatches.value[slashIndex.value]
      if (skill) activateSkill(skill)
      return
    }
    if (e.key === 'Escape') {
      e.preventDefault()
      text.value = ''
      return
    }
  }
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    submit()
  }
}

const ghostText = computed(() => (!text.value && props.previewText ? props.previewText : ''))

function resize() {
  const el = textarea.value
  if (!el) return
  const measure = ghostText.value
  if (measure) {
    const previous = el.value
    el.value = measure
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`
    el.value = previous
    return
  }
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 240)}px`
}

watch(ghostText, () => nextTick(resize))

function focus() {
  textarea.value?.focus()
}

defineExpose({ focus })
</script>

<template>
  <div
    :class="cn(
      'relative rounded-2xl border bg-background shadow-[0_2px_12px_-4px_rgba(0,0,0,0.08)] transition-shadow focus-within:shadow-[0_4px_20px_-6px_rgba(0,0,0,0.14)] focus-within:ring-1 focus-within:ring-ring/40',
      hero ? 'p-4' : 'p-3',
      dragging && 'ring-1 ring-foreground/30',
    )"
    @dragover.prevent="dragging = true"
    @dragleave="dragging = false"
    @drop="onDrop"
  >
    <div
      v-if="slashQuery !== null"
      class="absolute right-0 bottom-full left-0 z-30 mb-2 max-h-72 overflow-y-auto rounded-xl border bg-popover px-1.5 py-2 shadow-lg"
    >
      <div class="px-2.5 pb-1 text-[12px] text-muted-foreground">技能 ({{ slashMatches.length }})</div>
      <p v-if="!slashMatches.length" class="px-2.5 py-2 text-[13px] text-muted-foreground">没有匹配的技能</p>
      <button
        v-for="(skill, index) in slashMatches"
        :key="skill.name"
        type="button"
        :class="cn(
          'flex h-8 w-full items-center gap-2 rounded-lg px-2.5 text-left text-[13px]',
          index === slashIndex ? 'bg-sky-100 text-sky-950 dark:bg-sky-950/70 dark:text-sky-100' : 'hover:bg-muted/70',
        )"
        @mouseenter="slashIndex = index"
        @click="activateSkill(skill)"
      >
        <HammerIcon class="size-4 shrink-0 text-sky-500" />
        <span class="shrink-0 font-medium">{{ skill.title }}</span>
        <span class="min-w-0 flex-1 truncate text-muted-foreground">{{ skill.description }}</span>
        <PinIcon v-if="index === slashIndex" class="size-3.5 shrink-0 text-sky-700/70 dark:text-sky-200/70" />
      </button>
    </div>
    <div v-if="pending.length" class="mb-2 flex flex-wrap gap-2">
      <div
        v-for="item in pending"
        :key="item.key"
        class="flex max-w-full items-center gap-2 rounded-lg bg-muted py-1 pr-1 pl-1.5 text-[12px]"
      >
        <img v-if="item.preview" :src="item.preview" alt="" class="size-8 rounded-md object-cover" />
        <span class="max-w-40 truncate">{{ item.file.name }}</span>
        <button type="button" class="rounded-md p-1 text-muted-foreground hover:text-foreground" @click="removeFile(item.key)">
          <XIcon class="size-3.5" />
        </button>
      </div>
    </div>
    <div class="flex flex-wrap items-start gap-2">
      <span
        v-for="skill in selectedSkills"
        :key="skill.name"
        class="mt-0.5 inline-flex max-w-full shrink-0 items-center gap-1 rounded-full bg-sky-100 py-0.5 pr-1 pl-1.5 text-[13px] text-sky-900 dark:bg-sky-950/70 dark:text-sky-100"
      >
        <HammerIcon class="size-4 shrink-0 text-sky-500" />
        <span class="truncate">{{ skill.title }}</span>
        <button type="button" class="rounded-full p-0.5 hover:bg-sky-200/80 dark:hover:bg-sky-900" title="取消技能" @click="toggleSkill(skill)">
          <XIcon class="size-3" />
        </button>
      </span>
      <SparklesIcon v-if="hero && !selectedSkills.length" class="mt-1 size-4 shrink-0 text-violet-500/80" />
      <div class="relative min-w-0 flex-1">
        <div
          v-if="ghostText"
          class="pointer-events-none absolute inset-0 whitespace-pre-wrap text-[14px] leading-6 text-muted-foreground/45"
        >{{ ghostText }}</div>
        <textarea
          ref="textarea"
          v-model="text"
          :placeholder="ghostText ? '' : placeholder"
          :disabled="disabled"
          rows="1"
          :class="cn(
            'w-full resize-none bg-transparent text-[14px] leading-6 outline-none placeholder:text-muted-foreground/70 disabled:opacity-50',
            hero ? 'min-h-20' : 'min-h-6',
          )"
          @input="resize"
          @keydown="onKeydown"
          @paste="onPaste"
        />
      </div>
    </div>
    <div class="mt-2 flex items-center gap-1">
      <input ref="fileInput" type="file" multiple class="hidden" @change="onPick" />
      <div class="relative">
        <button
          type="button"
          :class="cn(
            'flex size-8 items-center justify-center rounded-full border text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50',
            attachOpen && 'bg-muted text-foreground',
          )"
          :title="attachOpen ? '关闭' : '添加'"
          :disabled="disabled || busy"
          @click="toggleAttach"
        >
          <XIcon v-if="attachOpen" class="size-4" />
          <PlusIcon v-else class="size-4" />
        </button>
        <div v-if="attachOpen" class="fixed inset-0 z-10" @click="closeAttach" />
        <div v-if="attachOpen" class="absolute bottom-full left-0 z-20 mb-2 flex items-end">
          <div class="w-44 overflow-hidden rounded-2xl border bg-popover py-1 text-popover-foreground shadow-lg">
            <button
              type="button"
              class="flex h-11 w-full items-center gap-3 px-3 text-left text-[14px] hover:bg-muted/70"
              @mouseenter="attachPage = 'files'"
              @click="pickFiles"
            >
              <PaperclipIcon class="size-4" />
              添加文件
            </button>
            <button
              type="button"
              :class="cn(
                'flex h-11 w-full items-center gap-2.5 px-3 text-left text-[14px]',
                attachPage === 'skills' ? 'bg-sky-100 text-sky-950 dark:bg-sky-950/70 dark:text-sky-100' : 'hover:bg-muted/70',
              )"
              @mouseenter="attachPage = 'skills'"
              @click="attachPage = 'skills'"
            >
              <HammerIcon class="size-4 shrink-0 text-sky-500" />
              <span class="min-w-0 flex-1">技能</span>
              <ChevronRightIcon class="size-3.5 shrink-0 text-muted-foreground" />
            </button>
          </div>
          <div
            v-if="attachPage === 'skills'"
            class="mb-1 ml-2 flex max-h-[28rem] w-80 flex-col overflow-hidden rounded-2xl border bg-popover text-popover-foreground shadow-lg"
          >
            <div class="border-b p-2">
              <div class="flex items-center gap-2 rounded-lg bg-sky-50 px-2.5 dark:bg-sky-950/40">
                <SearchIcon class="size-3.5 shrink-0 text-muted-foreground" />
                <input
                  ref="skillSearch"
                  v-model="skillQuery"
                  type="search"
                  placeholder="搜索技能"
                  class="h-8 w-full bg-transparent text-[13px] outline-none placeholder:text-muted-foreground"
                />
              </div>
            </div>
            <div class="min-h-0 flex-1 overflow-y-auto py-1">
              <p v-if="!attachSkills.length" class="px-3 py-6 text-center text-[13px] text-muted-foreground">没有匹配的技能</p>
              <button
                v-for="skill in attachSkills"
                :key="skill.name"
                type="button"
                class="flex w-full items-start gap-2.5 px-3 py-2 text-left hover:bg-muted/60"
                @click="chooseSkill(skill)"
              >
                <span :class="cn('flex size-7 shrink-0 items-center justify-center rounded-lg text-[13px] font-medium', skillTint(skill.name))">
                  {{ skillInitial(skill) }}
                </span>
                <span class="min-w-0">
                  <span class="block truncate text-[14px] leading-5 font-medium">{{ skill.title }}</span>
                  <span class="block truncate text-[12px] leading-5 text-muted-foreground">{{ skill.description }}</span>
                </span>
              </button>
            </div>
            <div class="border-t py-1">
              <button
                type="button"
                class="flex h-10 w-full items-center gap-2.5 px-3 text-left text-[13px] hover:bg-muted/60"
                @click="openSkillLibrary(true)"
              >
                <UploadIcon class="size-4" />
                从本地添加技能
              </button>
              <button
                type="button"
                class="flex h-10 w-full items-center gap-2.5 px-3 text-left text-[13px] hover:bg-muted/60"
                @click="openSkillLibrary(false)"
              >
                <SettingsIcon class="size-4" />
                管理技能
              </button>
            </div>
          </div>
        </div>
      </div>
      <div class="relative">
        <button
          type="button"
          :class="cn(
            'inline-flex h-8 items-center gap-1.5 rounded-full px-2 text-[13px] hover:bg-muted disabled:opacity-50',
            props.permission === 'full' ? 'text-orange-600' : 'text-muted-foreground',
          )"
          :disabled="disabled"
          @click="permissionOpen = !permissionOpen; attachOpen = false; menuOpen = false"
        >
          <component :is="permissionIcon" class="size-3.5" />
          {{ permissionLabel }}
        </button>
        <div v-if="permissionOpen" class="fixed inset-0 z-10" @click="permissionOpen = false" />
        <div v-if="permissionOpen" class="absolute bottom-full left-0 z-20 mb-2 w-72 overflow-hidden rounded-xl border bg-popover py-1 text-popover-foreground shadow-lg">
          <button
            v-for="item in permissions"
            :key="item.id"
            type="button"
            class="flex w-full items-start gap-2.5 px-3 py-2.5 text-left hover:bg-muted/70"
            @click="emit('update:permission', item.id); permissionOpen = false"
          >
            <component :is="item.icon" :class="cn('mt-0.5 size-4 shrink-0', item.id === 'full' ? 'text-orange-600' : 'text-muted-foreground')" />
            <span class="min-w-0 flex-1">
              <span :class="cn('block text-[13px] leading-5', item.id === 'full' && 'text-orange-600')">{{ item.label }}</span>
              <span :class="cn('block text-[12px] leading-5', item.id === 'full' ? 'text-orange-600/80' : 'text-muted-foreground')">{{ item.detail }}</span>
            </span>
            <CheckIcon v-if="item.id === props.permission" :class="cn('mt-0.5 size-3.5 shrink-0', item.id === 'full' && 'text-orange-600')" />
          </button>
        </div>
      </div>
      <div class="ml-auto flex items-center gap-3">
      <ContextMeter v-model:open="contextOpen" :limit="context.limit" :parts="contextParts" />
      <div class="relative min-w-0">
        <button
          type="button"
          class="flex max-w-full items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground disabled:opacity-50"
          :disabled="disabled"
          @click="toggleMenu"
        >
          <span class="truncate">{{ modelLabel }}</span>
          <span class="shrink-0">{{ effortLabel }}</span>
        </button>
        <div v-if="menuOpen" class="fixed inset-0 z-10" @click="menuOpen = false" />
        <div v-if="menuOpen" class="absolute right-0 bottom-full z-20 mb-2">
          <div class="relative w-64">
          <div class="overflow-hidden rounded-xl border bg-popover text-popover-foreground shadow-lg">
            <button
              type="button"
              :class="cn('flex w-full items-center gap-3 px-3 py-2.5 text-left text-[13px] hover:bg-muted/70', menuPage === 'model' && 'bg-muted')"
              @click="menuPage = 'model'"
            >
              <span class="shrink-0">模型</span>
              <span class="min-w-0 flex-1 truncate text-right text-muted-foreground">{{ modelLabel }}</span>
              <ChevronRightIcon class="size-3.5 shrink-0 text-muted-foreground" />
            </button>
            <button
              type="button"
              :class="cn('flex w-full items-center gap-3 border-t px-3 py-2.5 text-left text-[13px] hover:bg-muted/70', menuPage === 'effort' && 'bg-muted')"
              @click="menuPage = 'effort'"
            >
              <span class="shrink-0">推理等级</span>
              <span class="min-w-0 flex-1 truncate text-right text-muted-foreground">{{ effortLabel }}</span>
              <ChevronRightIcon class="size-3.5 shrink-0 text-muted-foreground" />
            </button>
          </div>
          <div
            v-if="menuPage !== 'main'"
            :class="cn(
              'absolute right-full mr-1 max-h-64 w-40 overflow-y-auto rounded-xl border bg-popover py-1 text-popover-foreground shadow-lg',
              menuPage === 'model' ? 'bottom-1/2' : 'bottom-0',
            )"
          >
            <template v-if="menuPage === 'model'">
              <button
                v-for="item in modelOptions"
                :key="item.id"
                type="button"
                class="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] hover:bg-muted/70"
                @click="chooseModel(item.id)"
              >
                <span class="min-w-0 flex-1 truncate">{{ item.label }}</span>
                <CheckIcon v-if="item.id === model" class="size-3.5 shrink-0" />
              </button>
            </template>
            <template v-else>
              <button
                v-for="item in efforts"
                :key="item.id"
                type="button"
                class="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] hover:bg-muted/70"
                @click="chooseEffort(item.id)"
              >
                <span class="min-w-0 flex-1">{{ item.label }}</span>
                <CheckIcon v-if="item.id === effort" class="size-3.5 shrink-0" />
              </button>
            </template>
          </div>
          </div>
        </div>
      </div>
      <Button
        v-if="busy"
        size="icon"
        class="rounded-full"
        title="停止"
        @click="emit('stop')"
      >
        <SquareIcon class="size-3.5 fill-current" />
      </Button>
      <Button
        v-else
        size="icon"
        class="rounded-full"
        :disabled="(!text.trim() && !pending.length && !selectedSkills.length) || disabled"
        title="发送（Enter）"
        @click="submit"
      >
        <ArrowUpIcon />
      </Button>
      </div>
    </div>
  </div>
</template>
