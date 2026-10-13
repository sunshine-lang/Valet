<script setup lang="ts">
import { KeyRoundIcon } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { useSessionsStore } from '@/stores/sessions'

withDefaults(defineProps<{ showLink?: boolean }>(), { showLink: true })
const sessions = useSessionsStore()
</script>

<template>
  <section role="status" class="rounded-2xl border border-sky-200 bg-sky-50/60 p-5 text-left dark:border-sky-900 dark:bg-sky-950/30">
    <div class="flex items-center gap-2 text-sm font-semibold">
      <KeyRoundIcon class="size-4 text-sky-600 dark:text-sky-400" />
      先配置模型，再开始对话
    </div>
    <p class="mt-2 text-sm leading-6 text-muted-foreground">
      {{ sessions.modelSetupMessage || '在「设置 → 模型」填写百炼 API Key 并选择模型，保存后即可开始。也可以在项目根目录配置 .env。' }}
    </p>
    <pre class="mt-3 overflow-x-auto rounded-lg bg-background px-3 py-2 font-mono text-xs">cp -n .env.example .env</pre>
    <p class="mt-2 text-xs leading-6 text-muted-foreground">
      填写 <code>DASHSCOPE_API_KEY</code>，可用 <code>DASHSCOPE_MODEL</code> 设置默认模型。
      修改 <code>.env</code> 后重启后端，再点击「重新检查」。
    </p>
    <div class="mt-4 flex flex-wrap items-center gap-2">
      <Button v-if="showLink" size="sm" class="rounded-lg" as-child>
        <RouterLink to="/settings/model">去配置模型</RouterLink>
      </Button>
      <Button variant="outline" size="sm" class="rounded-lg" @click="sessions.checkHealth()">重新检查</Button>
    </div>
  </section>
</template>
