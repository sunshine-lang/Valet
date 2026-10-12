<script setup lang="ts">
import { CheckIcon, PlusIcon, RefreshCwIcon, SearchIcon, UploadIcon, XIcon } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { toast } from 'vue-sonner'
import MarkdownText from '@/components/MarkdownText.vue'
import PageHeader from '@/components/PageHeader.vue'
import { Button } from '@/components/ui/button'
import { api, ApiError } from '@/lib/api'
import type { SkillDetail, SkillInfo } from '@/lib/types'
import { cn } from '@/lib/utils'

type Tab = 'market' | 'builtin' | 'installed'

const route = useRoute()
const skills = ref<SkillInfo[]>([])
const tab = ref<Tab>('market')
const query = ref('')
const selected = ref<SkillDetail | null>(null)
const loading = ref(true)
const adding = ref(false)
const importing = ref(false)
const installAfterImport = ref(true)
const draggingZip = ref(false)
const zipInput = ref<HTMLInputElement>()
const busyName = ref('')

const installedCount = computed(
  () => skills.value.filter((skill) => skill.source === 'user' || (skill.source === 'market' && skill.installed)).length,
)

const visible = computed(() => {
  const q = query.value.trim().toLowerCase()
  return skills.value.filter((skill) => {
    if (tab.value === 'market' && skill.source !== 'market') return false
    if (tab.value === 'builtin' && skill.source !== 'builtin') return false
    if (tab.value === 'installed' && !(skill.source === 'user' || (skill.source === 'market' && skill.installed))) {
      return false
    }
    if (!q) return true
    return [skill.title, skill.name, skill.description].some((text) => text.toLowerCase().includes(q))
  })
})

async function load() {
  loading.value = true
  try {
    skills.value = (await api.listSkills()).skills
    if (selected.value && !skills.value.some((skill) => skill.name === selected.value?.name)) {
      selected.value = null
    }
  } catch (error) {
    toast.error(error instanceof ApiError ? error.message : '技能加载失败')
  } finally {
    loading.value = false
  }
}

async function openSkill(skill: SkillInfo) {
  try {
    selected.value = await api.getSkill(skill.name)
  } catch (error) {
    toast.error(error instanceof ApiError ? error.message : '技能内容加载失败')
  }
}

async function install(skill: SkillInfo) {
  busyName.value = skill.name
  try {
    await api.installSkill(skill.name)
    await load()
    if (selected.value?.name === skill.name) await openSkill(skill)
  } catch (error) {
    toast.error(error instanceof ApiError ? error.message : '安装失败')
  } finally {
    busyName.value = ''
  }
}

async function removeUserSkill(skill: SkillInfo) {
  busyName.value = skill.name
  try {
    await api.removeSkill(skill.name)
    if (selected.value?.name === skill.name) selected.value = null
    await load()
  } catch (error) {
    toast.error(error instanceof ApiError ? error.message : '移除失败')
  } finally {
    busyName.value = ''
  }
}

function openZipPicker() {
  zipInput.value?.click()
}

async function importZip(file: File) {
  if (!file.name.toLowerCase().endsWith('.zip')) {
    toast.error('请上传 .zip 压缩包')
    return
  }
  importing.value = true
  try {
    const bytes = new Uint8Array(await file.arrayBuffer())
    let binary = ''
    const step = 0x8000
    for (let i = 0; i < bytes.length; i += step) {
      binary += String.fromCharCode(...bytes.subarray(i, i + step))
    }
    const result = await api.importSkill(file.name, btoa(binary), installAfterImport.value)
    toast.success(`已导入 ${result.title}`)
    adding.value = false
    await load()
    await openSkill({ name: result.name, title: result.title, description: '', source: 'user', installed: result.installed })
  } catch (error) {
    toast.error(error instanceof ApiError ? error.message : '导入失败')
  } finally {
    importing.value = false
    if (zipInput.value) zipInput.value.value = ''
  }
}

function onZipPick(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) void importZip(file)
}

function onZipDrop(event: DragEvent) {
  draggingZip.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) void importZip(file)
}

watch(
  () => route.query.import,
  (value) => {
    if (value === '1') adding.value = true
  },
  { immediate: true },
)

onMounted(load)
</script>

<template>
  <PageHeader title="技能">
    <template #actions>
      <div class="relative">
        <SearchIcon class="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <input
          v-model="query"
          type="search"
          placeholder="搜索技能"
          class="h-8 w-44 rounded-lg border bg-background pr-2 pl-8 text-[13px] outline-none placeholder:text-muted-foreground focus:ring-1 focus:ring-ring/40"
        />
      </div>
      <Button variant="outline" size="icon-sm" class="rounded-lg" title="刷新" @click="load">
        <RefreshCwIcon />
      </Button>
      <Button size="sm" class="rounded-lg" @click="adding = !adding">
        <PlusIcon />
        添加
      </Button>
    </template>
  </PageHeader>

  <div v-if="adding" class="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-6" @click.self="adding = false">
    <div class="w-full max-w-lg rounded-2xl border bg-background p-5 shadow-xl">
      <div class="flex items-center justify-between">
        <h2 class="text-[16px] font-semibold">导入技能</h2>
        <button type="button" class="rounded-md p-1 text-muted-foreground hover:bg-muted" @click="adding = false">
          <XIcon class="size-4" />
        </button>
      </div>
      <input ref="zipInput" type="file" accept=".zip,application/zip" class="hidden" @change="onZipPick" />
      <button
        type="button"
        :class="cn(
          'mt-4 flex w-full flex-col items-center justify-center rounded-xl border border-dashed px-6 py-10 text-muted-foreground hover:bg-muted/40',
          draggingZip && 'bg-muted/60 text-foreground',
        )"
        @click="openZipPicker"
        @dragover.prevent="draggingZip = true"
        @dragleave="draggingZip = false"
        @drop.prevent="onZipDrop"
      >
        <UploadIcon class="size-8" />
        <span class="mt-3 text-[14px]">{{ importing ? '正在导入…' : '拖拽文件或点击上传' }}</span>
      </button>
      <label class="mt-4 flex items-center gap-2 text-[13px]">
        <input v-model="installAfterImport" type="checkbox" class="size-4 accent-foreground" />
        导入后立即启用
      </label>
      <div class="mt-4 text-[13px] leading-6">
        <div class="font-medium">文件要求</div>
        <ul class="mt-1 list-disc pl-5 text-muted-foreground">
          <li>文件夹或者 .zip 需要包含 SKILL.md 文件</li>
          <li>.md 文件需包含 YAML 格式的技能名称和描述</li>
        </ul>
      </div>
    </div>
  </div>

  <div class="flex gap-6 border-b px-6">
    <button
      v-for="item in ([
        ['market', '市场'],
        ['builtin', '内置'],
        ['installed', `已安装 ${installedCount}`],
      ] as const)"
      :key="item[0]"
      type="button"
      :class="cn(
        'border-b-2 py-2.5 text-[13px]',
        tab === item[0] ? 'border-foreground font-medium' : 'border-transparent text-muted-foreground hover:text-foreground',
      )"
      @click="tab = item[0]"
    >
      {{ item[1] }}
    </button>
  </div>

  <div class="flex min-h-0 flex-1">
    <div class="min-w-0 flex-1 overflow-y-auto px-6 py-4">
      <p v-if="loading" class="py-12 text-center text-sm text-muted-foreground">加载中…</p>
      <p v-else-if="!visible.length" class="py-12 text-center text-sm text-muted-foreground">
        {{ query ? '没有匹配的技能' : '这一类里还没有技能' }}
      </p>
      <div v-else class="mx-auto flex max-w-3xl flex-col gap-2">
        <button
          v-for="skill in visible"
          :key="skill.name"
          type="button"
          :class="cn(
            'flex items-start gap-3 rounded-xl border px-4 py-3 text-left hover:bg-muted/50',
            selected?.name === skill.name && 'border-foreground/20 bg-muted/40',
          )"
          @click="openSkill(skill)"
        >
          <span class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-[11px] font-semibold">
            {{ skill.title.slice(0, 1) }}
          </span>
          <span class="min-w-0 flex-1">
            <span class="flex items-center gap-2">
              <span class="truncate text-[14px] font-medium">{{ skill.title }}</span>
              <span v-if="skill.title !== skill.name" class="font-mono text-[11px] text-muted-foreground">{{ skill.name }}</span>
            </span>
            <span class="mt-0.5 line-clamp-2 block text-[12px] leading-5 text-muted-foreground">
              {{ skill.description }}
            </span>
          </span>
          <CheckIcon v-if="skill.source === 'market' && skill.installed" class="mt-1 size-4 shrink-0 text-emerald-600" />
          <Button
            v-else-if="skill.source === 'market'"
            size="sm"
            variant="outline"
            class="rounded-lg"
            :disabled="busyName === skill.name"
            @click.stop="install(skill)"
          >
            使用
          </Button>
        </button>
      </div>
    </div>

    <aside v-if="selected" class="flex w-[420px] shrink-0 flex-col border-l">
      <div class="flex items-start justify-between gap-3 border-b px-5 py-4">
        <div class="min-w-0">
          <h2 class="truncate text-[15px] font-semibold">{{ selected.title }}</h2>
          <p class="mt-1 font-mono text-[11px] text-muted-foreground">{{ selected.name }}</p>
        </div>
        <Button
          v-if="selected.source === 'user'"
          size="sm"
          variant="outline"
          class="rounded-lg"
          :disabled="busyName === selected.name"
          @click="removeUserSkill(selected)"
        >
          移除
        </Button>
        <Button
          v-else-if="selected.source === 'market' && !selected.installed"
          size="sm"
          class="rounded-lg"
          :disabled="busyName === selected.name"
          @click="install(selected)"
        >
          使用
        </Button>
      </div>
      <div class="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        <p class="text-[13px] leading-6 text-muted-foreground">{{ selected.description }}</p>
        <MarkdownText :source="selected.body" class="mt-4 text-[14px] leading-7" />
      </div>
    </aside>
  </div>
</template>
