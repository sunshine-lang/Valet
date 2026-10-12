<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'

const route = useRoute()
const title = computed(() => String(route.meta.title ?? ''))
</script>

<template>
  <PageHeader :title="title" />
  <div class="flex flex-1 items-center justify-center text-sm text-muted-foreground">即将支持</div>
</template>
