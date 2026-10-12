import { defineStore } from 'pinia'
import { reactive } from 'vue'
import { api } from '@/lib/api'
import type { Run, Step } from '@/lib/types'

export interface RunTrace {
  run: Run
  steps: Step[]
}

/** 运行与步骤的缓存：流式事件实时写入，追踪面板和运行详情页从这里读。 */
export const useTraceStore = defineStore('traces', () => {
  const traces = reactive<Record<string, RunTrace>>({})

  function upsertRun(run: Run) {
    const existing = traces[run.id]
    if (existing) {
      existing.run = { ...existing.run, ...run, config_snapshot: run.config_snapshot ?? existing.run.config_snapshot }
    } else {
      traces[run.id] = { run, steps: [] }
    }
  }

  function upsertStep(step: Step) {
    const trace = traces[step.run_id]
    if (!trace) return
    const i = trace.steps.findIndex((s) => s.id === step.id)
    if (i >= 0) trace.steps[i] = step
    else {
      trace.steps.push(step)
      trace.steps.sort((a, b) => a.seq - b.seq)
    }
  }

  async function load(runId: string): Promise<RunTrace> {
    const data = await api.getRun(runId)
    traces[runId] = data
    return traces[runId]!
  }

  return { traces, upsertRun, upsertStep, load }
})
