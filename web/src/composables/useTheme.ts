import { useColorMode } from '@vueuse/core'
import { computed } from 'vue'

export function useTheme() {
  const mode = useColorMode({ storageKey: 'valet-theme', disableTransition: false })
  const isDark = computed(() => mode.value === 'dark')
  function toggle() {
    mode.value = isDark.value ? 'light' : 'dark'
  }
  return { isDark, toggle }
}
