import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { acceptHMRUpdate, createPinia, defineStore, setActivePinia } from 'pinia'
import ts from 'typescript'
import { computed, ref } from 'vue'

const source = await readFile(new URL('../src/stores/chat.ts', import.meta.url), 'utf8')

// 使用真实 Pinia 更新已有实例；依赖仅替换不涉及本次场景的网络、追踪和提示。
function loadStore(code, hot) {
  const dependencies = {
    acceptHMRUpdate,
    defineStore,
    computed,
    ref,
    hot,
    toast: { error() {} },
    api: {
      async updateMessageFeedback(messageId, feedback) {
        return { message_id: messageId, feedback }
      },
    },
    ApiError: class extends Error {},
    useSessionsStore: () => ({}),
    useTraceStore: () => ({}),
  }
  const prepared = code
    .replace(/^import .*\n/gm, '')
    .replace('export const useChatStore', 'const useChatStore')
    .replaceAll('import.meta.hot', 'hot')
  const compiled = ts.transpileModule(prepared, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
  }).outputText
  return new Function(...Object.keys(dependencies), `${compiled}\nreturn useChatStore;`)(
    ...Object.values(dependencies),
  )
}

test('热更新新增反馈方法时，已打开的对话保留消息且能点赞', async () => {
  setActivePinia(createPinia())
  const hot = {
    data: {},
    accept(handler) { this.handler = handler },
    invalidate() { assert.fail('热更新不应要求重建对话页面') },
  }
  // 模拟用户先打开旧页面，再热更新加入反馈方法。
  const oldSource = source
    .replace(/\n  async function setFeedback\([\s\S]*?\n  }\n/, '\n')
    .replace('\n    setFeedback,', '')
  const oldDefinition = loadStore(oldSource, hot)
  const opened = oldDefinition()
  opened.messages = [{ id: 'assistant-1', content: '现有回复', feedback: null }]
  assert.equal(opened.setFeedback, undefined)
  assert.equal(typeof hot.handler, 'function', '已有聊天状态必须注册热更新，才能接收新增反馈方法')

  const replacement = loadStore(source, { data: {}, accept() {} })
  hot.handler({ useChatStore: replacement })
  assert.equal(oldDefinition(), opened)
  assert.equal(opened.messages[0].content, '现有回复')
  assert.equal(typeof opened.setFeedback, 'function')
  const feedback = { rating: 'like', reasons: [], comment: '' }
  await opened.setFeedback('assistant-1', feedback)
  assert.deepEqual(opened.messages[0].feedback, feedback)
})
