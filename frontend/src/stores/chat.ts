import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { conversationsApi } from '../api'
import { ApiError } from '../api/http'
import type { ChatMessage, Citation, Conversation } from '../api/types'

function tempId() {
  return `local-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export const useChatStore = defineStore('chat', () => {
  const conversations = ref<Conversation[]>([])
  const currentId = ref<string | null>(null)
  const messages = ref<ChatMessage[]>([])
  const generating = ref(false)
  const streamingMessageId = ref<string | null>(null)
  const lastError = ref<string | null>(null)

  let controller: AbortController | null = null

  const current = computed(() => conversations.value.find((c) => c.id === currentId.value) ?? null)

  async function loadConversations() {
    conversations.value = await conversationsApi.list()
    if (!conversations.value.length) {
      await createConversation()
      return
    }
    if (!currentId.value || !conversations.value.some((c) => c.id === currentId.value)) {
      await select(conversations.value[0].id)
    }
  }

  async function createConversation() {
    const conv = await conversationsApi.create()
    conversations.value = [conv, ...conversations.value]
    await select(conv.id)
    return conv
  }

  async function select(id: string) {
    if (generating.value) stop()
    currentId.value = id
    messages.value = await conversationsApi.messages(id)
  }

  async function removeConversation(id: string) {
    await conversationsApi.remove(id)
    conversations.value = conversations.value.filter((c) => c.id !== id)
    if (currentId.value === id) {
      currentId.value = null
      messages.value = []
      if (conversations.value.length) await select(conversations.value[0].id)
      else await createConversation()
    }
  }

  function upsertAssistant(id: string, patch: Partial<ChatMessage>) {
    const idx = messages.value.findIndex((m) => m.id === id)
    if (idx === -1) return
    messages.value[idx] = { ...messages.value[idx], ...patch }
  }

  function bumpConversation(title?: string) {
    const conv = conversations.value.find((c) => c.id === currentId.value)
    if (!conv) return
    if (title && conv.title === '新会话') conv.title = title.slice(0, 20)
    conv.updated_at = new Date().toISOString()
    conversations.value = [conv, ...conversations.value.filter((c) => c.id !== conv.id)]
  }

  async function runStream(
    start: (handlers: Parameters<typeof conversationsApi.chat>[2], signal: AbortSignal) => Promise<void>,
    placeholderId: string,
  ) {
    generating.value = true
    lastError.value = null
    controller = new AbortController()
    let assistantId = placeholderId
    let content = ''
    let citations: Citation[] = []

    try {
      await start(
        {
          onStart: (id) => {
            if (id) {
              upsertAssistant(placeholderId, { id })
              assistantId = id
              streamingMessageId.value = id
            }
          },
          onCitations: (c) => {
            citations = c
            upsertAssistant(assistantId, { citations })
          },
          onDelta: (delta) => {
            content += delta
            upsertAssistant(assistantId, { content, status: 'streaming' })
          },
          onDone: (done) => {
            upsertAssistant(assistantId, {
              id: done.message_id,
              content,
              citations,
              prompt_tokens: done.prompt_tokens,
              completion_tokens: done.completion_tokens,
              status: done.status,
            })
            assistantId = done.message_id
          },
          onError: (err) => {
            lastError.value = err.message
            upsertAssistant(assistantId, { content, citations, status: 'error' })
          },
        },
        controller.signal,
      )
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        upsertAssistant(assistantId, { content, citations, status: 'stopped' })
      } else {
        lastError.value = err instanceof ApiError ? err.message : '网络错误，请重试'
        upsertAssistant(assistantId, { content, citations, status: 'error' })
      }
    } finally {
      const msg = messages.value.find((m) => m.id === assistantId)
      if (msg && msg.status === 'streaming') msg.status = 'completed'
      generating.value = false
      streamingMessageId.value = null
      controller = null
    }
  }

  async function send(question: string) {
    const convId = currentId.value
    if (!convId || generating.value) return
    const q = question.trim()
    if (!q) return

    const userMsg: ChatMessage = {
      id: tempId(),
      conversation_id: convId,
      role: 'user',
      content: q,
      citations: [],
      prompt_tokens: 0,
      completion_tokens: 0,
      status: 'pending',
      created_at: new Date().toISOString(),
    }
    const assistantMsg: ChatMessage = {
      ...userMsg,
      id: tempId(),
      role: 'assistant',
      content: '',
      status: 'streaming',
    }
    messages.value = [...messages.value, userMsg, assistantMsg]
    bumpConversation(q)

    await runStream(
      (handlers, signal) =>
        conversationsApi.chat(
          convId,
          q,
          {
            ...handlers,
            onStart: (id) => {
              const u = messages.value.find((m) => m.id === userMsg.id)
              if (u) u.status = 'completed'
              handlers.onStart?.(id)
            },
          },
          signal,
        ),
      assistantMsg.id,
    )

    const u = messages.value.find((m) => m.id === userMsg.id)
    if (u && u.status === 'pending') u.status = 'failed'
  }

  async function retryUser(messageId: string) {
    const idx = messages.value.findIndex((m) => m.id === messageId)
    if (idx === -1) return
    const question = messages.value[idx].content
    messages.value = messages.value.filter((_, i) => i !== idx && i !== idx + 1)
    await send(question)
  }

  async function regenerate(messageId: string) {
    const convId = currentId.value
    if (!convId || generating.value) return
    const idx = messages.value.findIndex((m) => m.id === messageId)
    if (idx === -1) return
    const placeholder: ChatMessage = {
      ...messages.value[idx],
      id: tempId(),
      content: '',
      citations: [],
      prompt_tokens: 0,
      completion_tokens: 0,
      status: 'streaming',
    }
    messages.value = [...messages.value.slice(0, idx), placeholder]
    await runStream((handlers, signal) => conversationsApi.regenerate(convId, messageId, handlers, signal), placeholder.id)
  }

  async function stop() {
    const convId = currentId.value
    const mid = streamingMessageId.value
    if (convId && mid) {
      try {
        await conversationsApi.stop(convId, mid)
      } catch {
        /* ignore */
      }
    }
    controller?.abort()
  }

  return {
    conversations,
    currentId,
    current,
    messages,
    generating,
    lastError,
    loadConversations,
    createConversation,
    select,
    removeConversation,
    send,
    retryUser,
    regenerate,
    stop,
  }
})
