<script setup lang="ts">
import { CheckIcon, CopyIcon, LoaderCircleIcon, ThumbsDownIcon, ThumbsUpIcon, XIcon } from '@lucide/vue'
import { computed, onBeforeUnmount, ref } from 'vue'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { ApiError } from '@/lib/api'
import type { FeedbackReason, Message, MessageFeedback } from '@/lib/types'
import { useChatStore } from '@/stores/chat'

const props = defineProps<{ message: Message }>()
const chat = useChatStore()
const copied = ref(false)
const saving = ref(false)
const feedbackOpen = ref(false)
const selected = ref<FeedbackReason[]>([])
const comment = ref('')
const actionBar = ref<HTMLElement>()
let copyTimer: ReturnType<typeof setTimeout> | undefined

const isAssistant = computed(() => props.message.role === 'assistant')
const copyLabel = computed(() => copied.value ? '已复制' : isAssistant.value ? '复制 AI 回复' : '复制用户消息')
const reasons: { value: FeedbackReason; label: string }[] = [
  { value: 'misunderstood_question', label: '误解了我的问题' },
  { value: 'context_error', label: '上下文理解错误' },
  { value: 'vague_answer', label: '回答模糊/不具体' },
  { value: 'code_error', label: '代码有错误' },
  { value: 'unprofessional_answer', label: '回答不专业' },
  { value: 'code_format', label: '代码格式问题' },
  { value: 'other', label: '其他原因' },
]

onBeforeUnmount(() => clearTimeout(copyTimer))

async function copy() {
  try {
    await navigator.clipboard.writeText(props.message.content)
    copied.value = true
    clearTimeout(copyTimer)
    copyTimer = setTimeout(() => (copied.value = false), 1500)
  } catch {
    toast.error('复制失败，请检查浏览器剪贴板权限')
  }
}

async function saveFeedback(feedback: MessageFeedback | null) {
  if (saving.value) return
  saving.value = true
  try {
    await chat.setFeedback(props.message.id, feedback)
    feedbackOpen.value = false
    if (feedback?.rating === 'dislike') toast.success('反馈已提交，感谢你的反馈')
  } catch (error) {
    toast.error(error instanceof ApiError ? error.message : '反馈保存失败，请重试')
  } finally {
    saving.value = false
  }
}

function like() {
  saveFeedback(props.message.feedback?.rating === 'like' ? null : { rating: 'like', reasons: [], comment: '' })
}

function dislike() {
  if (props.message.feedback?.rating === 'dislike') {
    saveFeedback(null)
    return
  }
  selected.value = []
  comment.value = ''
  feedbackOpen.value = true
}

function toggleReason(reason: FeedbackReason) {
  selected.value = selected.value.includes(reason)
    ? selected.value.filter((item) => item !== reason)
    : [...selected.value, reason]
  if (reason === 'other' && !selected.value.includes('other')) comment.value = ''
}

function submitFeedback() {
  if (!selected.value.length) return
  saveFeedback({
    rating: 'dislike',
    reasons: selected.value,
    comment: selected.value.includes('other') ? comment.value.trim() : '',
  })
}

function restoreFocus(event: Event) {
  event.preventDefault()
  actionBar.value?.querySelector<HTMLButtonElement>('button[aria-label="点踩"]')?.focus()
}
</script>

<template>
  <div ref="actionBar" class="flex items-center gap-0.5 text-muted-foreground" :data-message-id="message.id" :data-message-role="message.role">
    <Button type="button" variant="ghost" size="icon-sm" :aria-label="copyLabel" :title="copyLabel" @click="copy">
      <CheckIcon v-if="copied" class="size-4" />
      <CopyIcon v-else class="size-4" />
    </Button>
    <template v-if="isAssistant">
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        aria-label="点赞"
        :title="message.feedback?.rating === 'like' ? '取消点赞' : '点赞'"
        :aria-pressed="message.feedback?.rating === 'like'"
        :class="{ 'bg-muted text-foreground': message.feedback?.rating === 'like' }"
        :disabled="saving"
        @click="like"
      >
        <ThumbsUpIcon class="size-4" />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        aria-label="点踩"
        :title="message.feedback?.rating === 'dislike' ? '取消点踩' : '点踩'"
        :aria-pressed="message.feedback?.rating === 'dislike'"
        :class="{ 'bg-muted text-foreground': message.feedback?.rating === 'dislike' }"
        :disabled="saving"
        @click="dislike"
      >
        <ThumbsDownIcon class="size-4" />
      </Button>
      <Dialog v-model:open="feedbackOpen">
        <DialogContent
          class="max-h-[calc(100dvh-2rem)] gap-5 overflow-y-auto sm:max-w-lg"
          :show-close-button="false"
          @close-auto-focus="restoreFocus"
        >
          <DialogHeader class="pr-8 text-left">
            <DialogTitle class="text-lg">请选择不满意的原因</DialogTitle>
            <DialogDescription class="text-xs">可多选，帮助我们了解这条回复的问题。</DialogDescription>
          </DialogHeader>
          <DialogClose as-child>
            <Button type="button" variant="ghost" size="icon-sm" class="absolute top-4 right-4" aria-label="关闭反馈">
              <XIcon class="size-5" />
            </Button>
          </DialogClose>
          <div class="grid grid-cols-2 gap-2.5 sm:grid-cols-6" role="group" aria-label="不满意的原因">
            <Button
              v-for="(reason, index) in reasons"
              :key="reason.value"
              type="button"
              :variant="selected.includes(reason.value) ? 'default' : 'outline'"
              class="h-auto min-h-9 rounded-lg px-3 py-2 text-sm whitespace-normal last:col-span-2"
              :class="index < 4 ? 'sm:col-span-3' : 'sm:col-span-2'"
              :aria-pressed="selected.includes(reason.value)"
              :disabled="saving"
              @click="toggleReason(reason.value)"
            >
              {{ reason.label }}
            </Button>
          </div>
          <div v-if="selected.includes('other')" class="space-y-1.5">
            <Textarea v-model="comment" aria-label="其他原因说明" placeholder="请描述具体的原因（选填）" :maxlength="200" :disabled="saving" class="min-h-28 resize-y" />
            <p class="text-right text-xs text-muted-foreground" aria-live="polite">{{ comment.length }}/200</p>
          </div>
          <Button type="button" class="w-full rounded-lg" :disabled="!selected.length || saving" @click="submitFeedback">
            <LoaderCircleIcon v-if="saving" class="size-4 animate-spin" />
            {{ saving ? '提交中…' : '提交反馈' }}
          </Button>
        </DialogContent>
      </Dialog>
    </template>
  </div>
</template>
