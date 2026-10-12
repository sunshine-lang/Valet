<script setup lang="ts">
import { computed } from 'vue'
import { renderMarkdown } from '@/lib/markdown'

const props = defineProps<{ source: string; streaming?: boolean }>()
const html = computed(() => renderMarkdown(props.source))
</script>

<template>
  <div class="markdown-body" :class="{ 'is-streaming': streaming }" v-html="html" />
</template>

<style scoped>
.markdown-body :deep(> :first-child) {
  margin-top: 0;
}
.markdown-body :deep(> :last-child) {
  margin-bottom: 0;
}
.markdown-body :deep(p) {
  margin: 0.65em 0;
}
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0.45em 0;
  padding-left: 1.25em;
}
.markdown-body :deep(ul) {
  list-style: disc;
}
.markdown-body :deep(ol) {
  list-style: decimal;
}
.markdown-body :deep(li) {
  margin: 0.15em 0;
}
.markdown-body :deep(li > p) {
  margin: 0.1em 0;
}
.markdown-body :deep(strong) {
  font-weight: 600;
}
.markdown-body :deep(a) {
  text-decoration: underline;
  text-underline-offset: 2px;
}
.markdown-body :deep(code) {
  border-radius: 0.25rem;
  background: var(--muted);
  padding: 0.1em 0.35em;
  font-family: var(--font-mono);
  font-size: 0.92em;
}
.markdown-body :deep(pre) {
  margin: 0.65em 0;
  overflow-x: auto;
  border-radius: 0.5rem;
  background: var(--muted);
  padding: 0.75rem 0.9rem;
}
.markdown-body :deep(pre code) {
  background: transparent;
  padding: 0;
  font-size: 0.85em;
}
.markdown-body :deep(blockquote) {
  margin: 0.65em 0;
  border-left: 2px solid var(--border);
  padding-left: 0.75em;
  color: var(--muted-foreground);
}
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  font-weight: 600;
  line-height: 1.4;
  margin: 0.8em 0 0.3em;
}
.markdown-body :deep(h1) {
  font-size: 1.15em;
}
.markdown-body :deep(h2) {
  font-size: 1.08em;
}
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  font-size: 1em;
}
.markdown-body :deep(hr) {
  margin: 0.8em 0;
  border: 0;
  border-top: 1px solid var(--border);
}
.markdown-body :deep(table) {
  width: 100%;
  margin: 0.65em 0;
  border-collapse: collapse;
  font-size: 0.92em;
}
.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--border);
  padding: 0.35em 0.6em;
  text-align: left;
}
.markdown-body.is-streaming :deep(> p:last-child) {
  display: inline;
}
.markdown-body.is-streaming::after {
  content: '';
  display: inline-block;
  width: 0.375rem;
  height: 1rem;
  margin-left: 0.125rem;
  transform: translateY(0.15rem);
  border-radius: 0.125rem;
  background: color-mix(in oklab, var(--foreground) 60%, transparent);
  animation: markdown-caret 1s steps(1) infinite;
}
@keyframes markdown-caret {
  50% {
    opacity: 0;
  }
}
</style>
