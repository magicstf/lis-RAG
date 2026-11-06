import type { ApiEnvelope } from './types'

export class ApiError extends Error {
  code: number
  detail: unknown
  constructor(code: number, message: string, detail?: unknown) {
    super(message)
    this.code = code
    this.detail = detail
  }
}

async function parse<T>(res: Response): Promise<T> {
  let body: ApiEnvelope<T> | null = null
  try {
    body = (await res.json()) as ApiEnvelope<T>
  } catch {
    body = null
  }
  if (!res.ok || !body || body.code !== 0) {
    throw new ApiError(body?.code ?? res.status, body?.message ?? `请求失败（HTTP ${res.status}）`, body?.detail)
  }
  return body.data
}

export async function get<T>(url: string): Promise<T> {
  return parse<T>(await fetch(url))
}

export async function post<T>(url: string, body?: unknown): Promise<T> {
  return parse<T>(
    await fetch(url, {
      method: 'POST',
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  )
}

export async function del<T>(url: string): Promise<T> {
  return parse<T>(await fetch(url, { method: 'DELETE' }))
}

export async function upload<T>(url: string, file: File): Promise<T> {
  const form = new FormData()
  form.append('file', file)
  return parse<T>(await fetch(url, { method: 'POST', body: form }))
}
