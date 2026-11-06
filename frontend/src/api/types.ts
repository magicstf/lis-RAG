export interface ApiEnvelope<T> {
  code: number
  data: T
  message: string
  detail?: unknown
}

export type DocumentStatus = 'processing' | 'ready' | 'failed'

export interface DocumentItem {
  id: string
  filename: string
  file_type: string
  file_size: number
  status: DocumentStatus
  chunk_count: number
  chunk_size: number
  chunk_overlap: number
  error_msg: string | null
  created_at: string
}

export interface Paged<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface ChunkDetail {
  id: string
  document_id: string
  document_name: string | null
  seq: number
  content: string
  char_start: number
  char_end: number
  page_no: number | null
  section: string
}

export interface Citation {
  index: number
  chunk_id: string
  document_id: string
  document_name: string
  content: string
  page_no: number | null
  section: string
  score: number
}

export type MessageStatus = 'completed' | 'stopped' | 'error' | 'pending' | 'streaming' | 'failed'

export interface ChatMessage {
  id: string
  conversation_id: string
  role: 'user' | 'assistant'
  content: string
  citations: Citation[]
  prompt_tokens: number
  completion_tokens: number
  status: MessageStatus
  created_at: string
}

export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface EvalCase {
  id: string
  type: 'answerable' | 'refusal'
  question: string
  answer_points: string[]
  expects: { document: string; keywords: string[] }[]
}

export interface EvalDetail {
  id: string
  type: 'answerable' | 'refusal'
  question: string
  hit: boolean
  rank: number
  matched_chunk_ids: string[]
  gate_score: number
  answer_points: string[]
}

export interface EvalRun {
  id: string
  config: { chunk_size: number; chunk_overlap: number; use_hybrid: boolean; use_rerank: boolean; k: number }
  recall_at_k: number
  mrr: number
  refusal_rate: number
  case_count: number
  detail: EvalDetail[]
  created_at: string
}

export interface UsageDay {
  date: string
  prompt_tokens: number
  completion_tokens: number
  llm_calls: number
  embedding_calls: number
}
