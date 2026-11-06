import { defineStore } from 'pinia'
import { ref } from 'vue'
import { evalsApi, usageApi } from '../api'
import type { EvalRun, UsageDay } from '../api/types'

export const useEvalStore = defineStore('eval', () => {
  const runs = ref<EvalRun[]>([])
  const running = ref(false)
  const latest = ref<EvalRun | null>(null)
  const usage = ref<UsageDay[]>([])

  async function loadRuns() {
    runs.value = await evalsApi.runs()
    if (!latest.value && runs.value.length) latest.value = runs.value[0]
  }

  async function loadUsage() {
    usage.value = (await usageApi.daily()).days
  }

  async function run(body: Parameters<typeof evalsApi.run>[0]) {
    running.value = true
    try {
      const result = await evalsApi.run(body)
      latest.value = result
      runs.value = [result, ...runs.value]
      return result
    } finally {
      running.value = false
    }
  }

  return { runs, running, latest, usage, loadRuns, loadUsage, run }
})
