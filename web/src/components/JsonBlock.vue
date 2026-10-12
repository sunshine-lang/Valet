<script setup lang="ts">
import { CheckIcon, CopyIcon } from '@lucide/vue'
import { computed, ref } from 'vue'
import { prettyJson } from '@/lib/format'
import { cn } from '@/lib/utils'

const props = defineProps<{ value: unknown; class?: string }>()
const text = computed(() => prettyJson(props.value))
const copied = ref(false)

async function copy() {
  await navigator.clipboard.writeText(text.value)
  copied.value = true
  setTimeout(() => (copied.value = false), 1200)
}
</script>

<template>
  <div class="group relative">
    <pre
      :class="cn('max-h-80 overflow-auto rounded-lg bg-muted/60 p-3 font-mono text-[11.5px] leading-relaxed whitespace-pre-wrap break-all text-foreground/90', props.class)"
    >{{ text }}</pre>
    <button
      class="absolute top-2 right-2 hidden rounded-md bg-background/80 p-1 text-muted-foreground ring-1 ring-border hover:text-foreground group-hover:block"
      title="复制"
      @click="copy"
    >
      <CheckIcon v-if="copied" class="size-3.5" />
      <CopyIcon v-else class="size-3.5" />
    </button>
  </div>
</template>
