<script setup lang="ts">
import { MoonIcon, SunIcon } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useTheme } from '@/composables/useTheme'

defineProps<{ title: string; subtitle?: string }>()
const { isDark, toggle } = useTheme()
</script>

<template>
  <header class="flex h-14 shrink-0 items-center justify-between gap-4 border-b px-6">
    <div class="flex min-w-0 items-baseline gap-3">
      <h1 class="truncate text-[15px] font-semibold tracking-tight">{{ title }}</h1>
      <span v-if="subtitle" class="truncate text-xs text-muted-foreground">{{ subtitle }}</span>
    </div>
    <div class="flex items-center gap-2">
      <slot name="actions" />
      <Tooltip>
        <TooltipTrigger as-child>
          <Button variant="outline" size="icon-sm" class="rounded-lg" @click="toggle">
            <SunIcon v-if="isDark" />
            <MoonIcon v-else />
          </Button>
        </TooltipTrigger>
        <TooltipContent>{{ isDark ? '切换到浅色' : '切换到深色' }}</TooltipContent>
      </Tooltip>
    </div>
  </header>
</template>
