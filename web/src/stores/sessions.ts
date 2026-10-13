import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '@/lib/api'
import type { ChatSession, Usage } from '@/lib/types'

export const useSessionsStore = defineStore('sessions', () => {
  const sessions = ref<ChatSession[]>([])
  const usage = ref<Usage | null>(null)
  const agentName = ref('Valet')
  const llmConfigured = ref<boolean | null>(null)
  const modelSetupMessage = ref<string | null>(null)
  const backendOnline = ref<boolean | null>(null)

  async function refresh() {
    try {
      sessions.value = await api.listSessions()
      backendOnline.value = true
    } catch {
      backendOnline.value = false
    }
  }

  async function refreshUsage() {
    try {
      usage.value = await api.usageToday()
    } catch {
      usage.value = null
    }
  }

  async function checkHealth() {
    try {
      const h = await api.health()
      llmConfigured.value = h.llm_configured
      modelSetupMessage.value = h.setup_message
      backendOnline.value = true
      if (h.name) {
        agentName.value = h.name
        document.title = h.name
      }
    } catch {
      backendOnline.value = false
    }
  }

  async function remove(id: string) {
    await api.deleteSession(id)
    sessions.value = sessions.value.filter((s) => s.id !== id)
  }

  return {
    sessions,
    usage,
    agentName,
    llmConfigured,
    modelSetupMessage,
    backendOnline,
    refresh,
    refreshUsage,
    checkHealth,
    remove,
  }
})
