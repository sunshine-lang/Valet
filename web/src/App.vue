<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import AppSidebar from '@/components/AppSidebar.vue'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useTheme } from '@/composables/useTheme'
import { useSessionsStore } from '@/stores/sessions'

useTheme()
const sessions = useSessionsStore()
const route = useRoute()
const isSettings = computed(() => route.path.startsWith('/settings'))

onMounted(() => {
  sessions.checkHealth()
  sessions.refresh()
  sessions.refreshUsage()
})
</script>

<template>
  <TooltipProvider :delay-duration="300">
    <div v-if="isSettings" class="h-full overflow-hidden">
      <RouterView />
    </div>
    <div v-else class="flex h-full overflow-hidden">
      <AppSidebar />
      <main class="flex min-w-0 flex-1 flex-col bg-background">
        <RouterView />
      </main>
    </div>
    <Toaster position="top-center" rich-colors />
  </TooltipProvider>
</template>
