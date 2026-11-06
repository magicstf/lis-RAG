import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function highlight(code: string, lang: string): string {
  if (lang && hljs.getLanguage(lang)) {
    try {
      return `<pre class="hljs"><code>${hljs.highlight(code, { language: lang, ignoreIllegals: true }).value}</code></pre>`
    } catch {
      /* fall through */
    }
  }
  return `<pre class="hljs"><code>${escapeHtml(code)}</code></pre>`
}

const md: MarkdownIt = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  highlight,
})

const CITE_RE = /\[(\d{1,2})\]/g

/** Render markdown and turn [n] markers into clickable citation tags. */
export function renderMarkdown(text: string): string {
  const html = md.render(text || '')
  return html.replace(CITE_RE, (_m: string, n: string) => `<span class="cite-tag" data-cite="${n}">${n}</span>`)
}

export function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(2)} MB`
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN', { hour12: false })
}
