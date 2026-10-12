<script setup lang="ts">
import { ShieldQuestionIcon } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type { PendingConfirmation } from '@/lib/types'
import { useSessionsStore } from '@/stores/sessions'

defineProps<{ pending: PendingConfirmation; disabled?: boolean }>()
const sessions = useSessionsStore()
const emit = defineEmits<{ decide: [choice: 'once' | 'session' | 'reject'] }>()

const actionLabel: Record<string, string> = {
  read: '读取项目外的文件',
  write: '修改项目外的文件',
  network: '联网',
  command: '运行命令',
}

function display(v: unknown) {
  return typeof v === 'string' ? v : JSON.stringify(v)
}
</script>

<template>
  <div class="rounded-xl border border-amber-500/30 bg-amber-500/[0.06] p-4">
    <div class="flex items-start gap-3">
      <div class="flex size-8 shrink-0 items-center justify-center rounded-lg bg-amber-500/15 text-amber-600 dark:text-amber-400">
        <ShieldQuestionIcon class="size-4" />
      </div>
      <div class="min-w-0 flex-1">
        <div class="text-[13px] font-semibold">需要你的确认</div>
        <p class="mt-0.5 text-xs text-muted-foreground">
          {{ pending.reason || `${sessions.agentName} 想调用 ${pending.tool_name}` }}
        </p>
        <dl class="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 rounded-lg bg-background/70 p-3 text-[13px] ring-1 ring-border">
          <template v-for="(value, key) in pending.arguments" :key="key">
            <dt class="font-mono text-xs leading-5 text-muted-foreground">{{ key }}</dt>
            <dd class="break-all">{{ display(value) }}</dd>
          </template>
        </dl>
        <div class="mt-3 flex flex-wrap gap-2">
          <Button size="sm" class="rounded-lg" :disabled="disabled" @click="emit('decide', 'once')">本次允许</Button>
          <Button
            v-if="pending.action"
            size="sm"
            variant="outline"
            class="rounded-lg"
            :disabled="disabled"
            @click="emit('decide', 'session')"
          >
            本对话允许{{ actionLabel[pending.action] ? `：${actionLabel[pending.action]}` : '' }}
          </Button>
          <Button size="sm" variant="outline" class="rounded-lg" :disabled="disabled" @click="emit('decide', 'reject')">
            拒绝
          </Button>
        </div>
      </div>
    </div>
  </div>
</template>
