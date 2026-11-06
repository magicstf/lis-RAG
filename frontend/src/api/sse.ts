import { ApiError } from './http'
import type { Citation } from './types'

export interface DoneEvent {
  message_id: string
  prompt_tokens: number
  completion_tokens: number
  status: 'completed' | 'stopped' | 'error'
}

export interface SseHandlers {
  onStart?: (assistantMessageId: string | null) => void
  onCitations?: (citations: Citation[]) => void
  onDelta?: (content: string) => void
  onDone?: (done: DoneEvent) => void
  onError?: (err: { code: number; message: string }) => void
}

/**
 * POST + ReadableStream based SSE client (EventSource only supports GET).
 */
export async function streamChat(url: string, body: unknown, handlers: SseHandlers, signal?: AbortSignal): Promise<void> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  })

  if (!res.ok || !res.body) {
    let payload: { code?: number; message?: string } | null = null
    try {
      payload = await res.json()
    } catch {
      payload = null
    }
    throw new ApiError(payload?.code ?? res.status, payload?.message ?? `请求失败（HTTP ${res.status}）`)
  }

  handlers.onStart?.(res.headers.get('X-Assistant-Message-Id'))

  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  const dispatch = (block: string) => {
    let event = 'message'
    const dataLines: string[] = []
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
    }
    if (!dataLines.length) return
    let data: any
    try {
      data = JSON.parse(dataLines.join('\n'))
    } catch {
      return
    }
    switch (event) {
      case 'citations':
        handlers.onCitations?.(data.citations ?? [])
        break
      case 'delta':
        handlers.onDelta?.(data.content ?? '')
        break
      case 'done':
        handlers.onDone?.(data as DoneEvent)
        break
      case 'error':
        handlers.onError?.(data)
        break
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx: number
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      if (block.trim()) dispatch(block)
    }
  }
  if (buffer.trim()) dispatch(buffer)
}
