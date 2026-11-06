import { del, get, post, upload } from './http'
import { streamChat, type SseHandlers } from './sse'
import type {
  ChatMessage,
  ChunkDetail,
  Conversation,
  DocumentItem,
  EvalCase,
  EvalRun,
  Paged,
  UsageDay,
} from './types'

export const documentsApi = {
  list: (page = 1, pageSize = 100) => get<Paged<DocumentItem>>(`/api/documents?page=${page}&page_size=${pageSize}`),
  upload: (file: File) => upload<DocumentItem>('/api/documents', file),
  remove: (id: string) => del<{ deleted: boolean }>(`/api/documents/${id}`),
  reindex: (id: string, body: { chunk_size?: number; chunk_overlap?: number }) =>
    post<DocumentItem>(`/api/documents/${id}/reindex`, body),
  chunk: (documentId: string, chunkId: string) =>
    get<ChunkDetail>(`/api/documents/${documentId}/chunks/${chunkId}`),
}

export const conversationsApi = {
  list: () => get<Conversation[]>('/api/conversations'),
  create: () => post<Conversation>('/api/conversations'),
  remove: (id: string) => del<{ deleted: boolean }>(`/api/conversations/${id}`),
  messages: (id: string) => get<ChatMessage[]>(`/api/conversations/${id}/messages`),
  chat: (id: string, question: string, handlers: SseHandlers, signal?: AbortSignal) =>
    streamChat(`/api/conversations/${id}/chat`, { question }, handlers, signal),
  regenerate: (id: string, messageId: string, handlers: SseHandlers, signal?: AbortSignal) =>
    streamChat(`/api/conversations/${id}/regenerate`, { message_id: messageId }, handlers, signal),
  stop: (id: string, messageId: string) => post<{ stopped: boolean }>(`/api/conversations/${id}/stop`, { message_id: messageId }),
}

export const evalsApi = {
  cases: () => get<{ cases: EvalCase[] }>('/api/evals/cases'),
  run: (body: { chunk_size?: number; chunk_overlap?: number; use_hybrid?: boolean; use_rerank?: boolean; k?: number }) =>
    post<EvalRun>('/api/evals/run', body),
  runs: () => get<EvalRun[]>('/api/evals/runs'),
}

export const usageApi = {
  daily: () => get<{ days: UsageDay[] }>('/api/usage/daily'),
}
