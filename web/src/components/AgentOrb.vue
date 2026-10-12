<script setup lang="ts">
import { cn } from '@/lib/utils'

const props = withDefaults(defineProps<{ size?: 'sm' | 'md' | 'lg'; active?: boolean }>(), {
  size: 'lg',
  active: false,
})

const sizeClass = { sm: 'size-8', md: 'size-10', lg: 'size-20' }
</script>

<template>
  <div
    :class="cn('relative shrink-0', sizeClass[props.size])"
    :style="{ animation: `orb-breathe ${props.active ? 1.6 : 5}s ease-in-out infinite` }"
    aria-hidden="true"
  >
    <div
      class="absolute -inset-1 rounded-full opacity-60 blur-md"
      :style="{
        background: 'conic-gradient(from 0deg, #a5b4fc, #c4b5fd, #f5d0fe, #bae6fd, #a5b4fc)',
        animation: `orb-spin ${props.active ? 2.5 : 10}s linear infinite`,
      }"
    />
    <div
      class="absolute inset-0 rounded-full"
      :style="{
        background:
          'radial-gradient(circle at 32% 28%, rgba(255,255,255,0.95), rgba(255,255,255,0.45) 30%, transparent 62%), conic-gradient(from 200deg, #c7d2fe, #e9d5ff, #fbcfe8, #bfdbfe, #c7d2fe)',
        animation: `orb-spin ${props.active ? 4 : 16}s linear infinite reverse`,
      }"
    />
    <div
      class="absolute inset-0 rounded-full ring-1 ring-white/70 shadow-[inset_0_-6px_18px_rgba(99,102,241,0.28)] dark:ring-white/20"
    />
  </div>
</template>
