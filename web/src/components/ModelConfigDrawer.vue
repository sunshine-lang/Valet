<script setup lang="ts">
import { ExternalLinkIcon, EyeIcon, EyeOffIcon, LoaderCircleIcon } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import ModelSetupNotice from '@/components/ModelSetupNotice.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { api, ApiError } from '@/lib/api'
import type { AgentConfig, ProviderInfo } from '@/lib/types'
import { useSessionsStore } from '@/stores/sessions'

const INPUT_PRESETS = [
  { label: '32K', value: 32_768 },
  { label: '64K', value: 65_536 },
  { label: '128K', value: 131_072 },
  { label: '256K', value: 262_144 },
]
const OUTPUT_PRESETS = [
  { label: '8K', value: 8_192 },
  { label: '16K', value: 16_384 },
  { label: '32K', value: 32_768 },
  { label: '64K', value: 65_536 },
]

const sessions = useSessionsStore()

const OTHER_MODEL = '__other__'

const loaded = ref<AgentConfig | null>(null)
const providers = ref<ProviderInfo[]>([])
const provider = ref('dashscope')
const apiBase = ref('')
const apiKey = ref('')
const showKey = ref(false)
const model = ref('')
const toolCalling = ref(true)
const imageInput = ref(false)
const customProtocol = ref(false)
const maxInput = ref<number | null>(null)
const maxOutput = ref<number | null>(null)
const inputText = ref('')
const outputText = ref('')
const saving = ref(false)
const testing = ref(false)

const currentProvider = computed(() => providers.value.find((item) => item.id === provider.value))
const modelChoice = computed(() => {
  const models = currentProvider.value?.models ?? []
  if (!models.length) return ''
  return models.some((item) => item.id === model.value) ? model.value : OTHER_MODEL
})
const keyPlaceholder = computed(() => {
  const savedBase = loaded.value?.api_base || currentProvider.value?.base_url || ''
  const nextBase = apiBase.value.trim() || currentProvider.value?.base_url || ''
  if (loaded.value?.api_key_set && loaded.value.provider === provider.value && savedBase === nextBase) return '已保存，留空则不修改'
  const current = currentProvider.value
  if (current?.env_key_set) return `留空则使用环境变量 ${current.env_key}`
  if (current?.env_key) return `输入 API Key，或设置 ${current.env_key}`
  return '输入你的 API Key'
})

const catalogModel = computed(() =>
  currentProvider.value?.models.find((item) => item.id === model.value),
)
const showAdvanced = computed(() => provider.value === 'custom' || !catalogModel.value)
const capabilityText = computed(() => {
  const item = catalogModel.value
  if (!item) return ''
  return [item.tools ? '支持工具调用' : '不支持工具调用', item.image ? '支持图片' : '仅文本'].join(' · ')
})

const checks = computed(() => [
  {
    key: 'tool',
    label: '工具调用',
    hint: '把文件、搜索等工具交给模型',
    get: () => toolCalling.value,
    set: (v: boolean) => (toolCalling.value = v),
  },
  {
    key: 'image',
    label: '图片输入',
    hint: '允许把图片发给模型',
    get: () => imageInput.value,
    set: (v: boolean) => (imageInput.value = v),
  },
  {
    key: 'proto',
    label: '自定义协议',
    hint: '不附加思考参数，适合不完全兼容 OpenAI 的接口',
    get: () => customProtocol.value,
    set: (v: boolean) => (customProtocol.value = v),
  },
])

function textFor(value: number | null, presets: { label: string; value: number }[]) {
  if (value == null) return ''
  return presets.find((item) => item.value === value)?.label ?? String(value)
}

function parseContext(raw: string, presets: { label: string; value: number }[]) {
  const text = raw.trim()
  if (!text) return null
  const preset = presets.find((item) => item.label.toLowerCase() === text.toLowerCase())
  if (preset) return preset.value
  const numeric = Number(text.replace(/[,\s_]/g, ''))
  if (!Number.isFinite(numeric) || numeric < 1) return null
  return Math.round(numeric)
}

function apply(config: AgentConfig) {
  loaded.value = config
  provider.value = config.provider || 'dashscope'
  if (provider.value === 'custom' && !config.api_base) provider.value = 'dashscope'
  apiBase.value = config.api_base
  apiKey.value = ''
  showKey.value = false
  model.value = config.model
  toolCalling.value = config.tool_calling
  imageInput.value = config.image_input
  customProtocol.value = config.custom_protocol
  maxInput.value = config.max_input_tokens
  maxOutput.value = config.max_output_tokens
  inputText.value = textFor(config.max_input_tokens, INPUT_PRESETS)
  outputText.value = textFor(config.max_output_tokens, OUTPUT_PRESETS)
}

async function load() {
  const [res, list] = await Promise.all([api.getAgentConfig(), api.listProviders(), sessions.checkHealth()])
  providers.value = list
  apply(res.config)
}

function onProvider(value: string) {
  const next = providers.value.find((item) => item.id === value)
  const previous = currentProvider.value
  if (!next) return
  const baseWasDefault = !apiBase.value || apiBase.value === previous?.base_url
  provider.value = value
  apiKey.value = ''
  showKey.value = false
  if (baseWasDefault) apiBase.value = next.base_url
  const ids = next.models.map((item) => item.id)
  if (ids.length && !ids.includes(model.value)) model.value = ids[0]
}

function onModelChoice(value: string) {
  if (value === OTHER_MODEL) {
    if (currentProvider.value?.models.some((item) => item.id === model.value)) model.value = ''
    return
  }
  model.value = value
}

onMounted(() => {
  load().catch(() => toast.error('模型配置加载失败'))
})

function pick(which: 'input' | 'output', preset: { label: string; value: number }) {
  if (which === 'input') {
    const same = maxInput.value === preset.value
    maxInput.value = same ? null : preset.value
    inputText.value = same ? '' : preset.label
  } else {
    const same = maxOutput.value === preset.value
    maxOutput.value = same ? null : preset.value
    outputText.value = same ? '' : preset.label
  }
}

function onInputText(raw: string) {
  inputText.value = raw
  maxInput.value = parseContext(raw, INPUT_PRESETS)
}

function onOutputText(raw: string) {
  outputText.value = raw
  maxOutput.value = parseContext(raw, OUTPUT_PRESETS)
}

async function save() {
  if (!loaded.value || !model.value.trim()) return
  saving.value = true
  try {
    const res = await api.updateAgentConfig({
      ...loaded.value,
      provider: provider.value,
      api_base: apiBase.value.trim(),
      api_key: apiKey.value.trim(),
      model: model.value.trim(),
      tool_calling: toolCalling.value,
      image_input: imageInput.value,
      custom_protocol: customProtocol.value,
      max_input_tokens: maxInput.value,
      max_output_tokens: maxOutput.value,
    })
    apply(res.config)
    await sessions.checkHealth()
    if (sessions.llmConfigured) toast.success('模型配置已保存，可以开始对话')
    else toast.message('模型选项已保存，请继续填写 API Key')
  } catch (error) {
    toast.error(error instanceof ApiError ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}

async function testConnection() {
  if (!model.value.trim()) {
    toast.error('请先填写模型名称')
    return
  }
  testing.value = true
  try {
    await api.testModel({
      provider: provider.value,
      api_base: apiBase.value.trim(),
      api_key: apiKey.value.trim(),
      model: model.value.trim(),
      thinking: loaded.value?.thinking ?? false,
    })
    toast.success('连接成功')
  } catch (error) {
    toast.error(error instanceof ApiError ? error.message : '连接失败')
  } finally {
    testing.value = false
  }
}
</script>

<template>
  <div class="max-w-xl space-y-4">
      <ModelSetupNotice v-if="sessions.llmConfigured === false" :show-link="false" />
      <div v-if="loaded" class="space-y-4 rounded-2xl border p-5">
        <div class="space-y-1.5">
          <div class="flex items-center justify-between gap-2">
            <Label>供应商（OpenAI 兼容 API）</Label>
            <a
              v-if="currentProvider?.docs_url"
              :href="currentProvider.docs_url"
              :aria-label="`查看${currentProvider.name}官方 API 文档`"
              target="_blank"
              rel="noopener noreferrer"
              class="inline-flex shrink-0 items-center gap-1 text-xs text-muted-foreground hover:text-foreground hover:underline"
            >
              查看文档
              <ExternalLinkIcon class="size-3.5" aria-hidden="true" />
            </a>
          </div>
          <Select :model-value="provider" @update:model-value="(value) => onProvider(String(value))">
            <SelectTrigger class="w-full"><SelectValue placeholder="选择供应商" /></SelectTrigger>
            <SelectContent>
              <SelectItem v-for="item in providers" :key="item.id" :value="item.id">{{ item.name }}</SelectItem>
            </SelectContent>
          </Select>
          <p class="text-xs text-muted-foreground">当前项目已验证阿里云百炼的 12 个模型。填写 API Key 后可先测试连接，再保存配置。</p>
        </div>

        <div class="space-y-1.5">
          <Label for="api-base">接口地址</Label>
          <Input
            id="api-base"
            v-model="apiBase"
            :placeholder="currentProvider?.base_url || 'https://api.example.com/v1'"
            autocomplete="off"
          />
          <p v-if="provider !== 'custom' && currentProvider?.base_url" class="text-xs text-muted-foreground">
            留空则使用 {{ currentProvider.base_url }}
          </p>
        </div>

        <div class="space-y-1.5">
          <Label for="api-key">API Key</Label>
          <div class="flex gap-2">
            <div class="relative min-w-0 flex-1">
              <Input
                id="api-key"
                v-model="apiKey"
                :type="showKey ? 'text' : 'password'"
                class="pr-9"
                :placeholder="keyPlaceholder"
                autocomplete="off"
              />
              <button
                type="button"
                class="absolute top-1/2 right-2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                @click="showKey = !showKey"
              >
                <EyeOffIcon v-if="showKey" class="size-4" />
                <EyeIcon v-else class="size-4" />
              </button>
            </div>
            <Button variant="outline" size="sm" class="h-9 shrink-0 rounded-lg" :disabled="testing" @click="testConnection">
              <LoaderCircleIcon v-if="testing" class="animate-spin" />
              测试连接
            </Button>
          </div>
        </div>

        <div class="space-y-1.5">
          <Label for="model-name">模型</Label>
          <Select
            v-if="currentProvider?.models.length"
            :model-value="modelChoice"
            @update:model-value="(value) => onModelChoice(String(value))"
          >
            <SelectTrigger id="model-name" class="w-full"><SelectValue placeholder="选择模型" /></SelectTrigger>
            <SelectContent>
              <SelectItem v-for="item in currentProvider.models" :key="item.id" :value="item.id">
                {{ item.label }}
              </SelectItem>
              <SelectItem :value="OTHER_MODEL">其他模型…</SelectItem>
            </SelectContent>
          </Select>
          <Input
            v-if="!currentProvider?.models.length || modelChoice === OTHER_MODEL"
            id="model-id"
            v-model="model"
            class="font-mono"
            placeholder="输入模型 ID，例如 gpt-4.1"
            maxlength="128"
            autocomplete="off"
          />
          <p v-if="capabilityText" class="text-xs text-muted-foreground">{{ capabilityText }}</p>
        </div>

        <template v-if="showAdvanced">
        <div class="space-y-2">
          <div class="text-sm font-medium">高级配置</div>
          <p class="text-xs text-muted-foreground">目录里的模型会自动带上这些能力。只有自定义供应商，或手填的模型 ID，才需要自己选。</p>
          <div class="divide-y rounded-xl border px-3">
            <div v-for="item in checks" :key="item.key" class="flex items-center justify-between gap-4 py-3">
              <span>
                <span class="block text-[13px]">{{ item.label }}</span>
                <span class="mt-0.5 block text-xs text-muted-foreground">{{ item.hint }}</span>
              </span>
              <Switch :model-value="item.get()" @update:model-value="(value) => item.set(value === true)" />
            </div>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div class="space-y-1.5">
            <Label for="max-input">输入</Label>
            <Input
              id="max-input"
              :model-value="inputText"
              placeholder="使用提供商默认值"
              @update:model-value="(value) => onInputText(String(value))"
            />
            <div class="flex gap-3 text-xs text-muted-foreground">
              <button
                v-for="preset in INPUT_PRESETS"
                :key="preset.label"
                type="button"
                class="rounded-md px-1.5 py-0.5 hover:bg-muted hover:text-foreground"
                :class="maxInput === preset.value && 'bg-muted font-medium text-foreground'"
                @click="pick('input', preset)"
              >
                {{ preset.label }}
              </button>
            </div>
          </div>
          <div class="space-y-1.5">
            <Label for="max-output">输出</Label>
            <Input
              id="max-output"
              :model-value="outputText"
              placeholder="使用提供商默认值"
              @update:model-value="(value) => onOutputText(String(value))"
            />
            <div class="flex gap-3 text-xs text-muted-foreground">
              <button
                v-for="preset in OUTPUT_PRESETS"
                :key="preset.label"
                type="button"
                class="rounded-md px-1.5 py-0.5 hover:bg-muted hover:text-foreground"
                :class="maxOutput === preset.value && 'bg-muted font-medium text-foreground'"
                @click="pick('output', preset)"
              >
                {{ preset.label }}
              </button>
            </div>
          </div>
        </div>
        </template>

        <div class="flex justify-end border-t pt-4">
          <Button size="sm" class="rounded-lg" :disabled="saving || !model.trim()" @click="save">
            保存
          </Button>
        </div>
      </div>
      <p v-else class="text-sm text-muted-foreground">加载中…</p>
  </div>
</template>
