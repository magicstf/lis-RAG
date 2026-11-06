import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { documentsApi } from '../api'
import type { DocumentItem } from '../api/types'

export const useDocumentsStore = defineStore('documents', () => {
  const items = ref<DocumentItem[]>([])
  const loading = ref(false)
  let timer: ReturnType<typeof setTimeout> | null = null

  const hasProcessing = computed(() => items.value.some((d) => d.status === 'processing'))
  const readyCount = computed(() => items.value.filter((d) => d.status === 'ready').length)

  async function fetchList() {
    loading.value = true
    try {
      const data = await documentsApi.list(1, 200)
      items.value = data.items
    } finally {
      loading.value = false
    }
    schedulePoll()
  }

  function schedulePoll() {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
    if (hasProcessing.value) {
      timer = setTimeout(() => {
        fetchList().catch(() => schedulePoll())
      }, 2000)
    }
  }

  function stopPolling() {
    if (timer) clearTimeout(timer)
    timer = null
  }

  async function upload(file: File) {
    const doc = await documentsApi.upload(file)
    items.value = [doc, ...items.value.filter((d) => d.id !== doc.id)]
    schedulePoll()
    return doc
  }

  async function remove(id: string) {
    await documentsApi.remove(id)
    items.value = items.value.filter((d) => d.id !== id)
  }

  async function reindex(id: string, body: { chunk_size?: number; chunk_overlap?: number }) {
    const doc = await documentsApi.reindex(id, body)
    items.value = items.value.map((d) => (d.id === id ? doc : d))
    schedulePoll()
  }

  return { items, loading, hasProcessing, readyCount, fetchList, stopPolling, upload, remove, reindex }
})
