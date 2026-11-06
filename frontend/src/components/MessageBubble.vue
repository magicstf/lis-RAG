<script setup lang="ts">
import { computed } from 'vue'
import type { ChatMessage, Citation } from '../api/types'
import { renderMarkdown } from '../utils/markdown'
import CitationCard from './CitationCard.vue'

const props = defineProps<{ message: ChatMessage; disabled?: boolean }>()
const emit = defineEmits<{
  (e: 'open-citation', citation: Citation): void
  (e: 'regenerate', id: string): void
  (e: 'retry', id: string): void
}>()

const isUser = computed(() => props.message.role === 'user')
const streaming = computed(() => props.message.status === 'streaming')
const html = computed(() => renderMarkdown(props.message.content))
const tokens = computed(() => props.message.prompt_tokens + props.message.completion_tokens)

function onBodyClick(e: MouseEvent) {
  const target = (e.target as HTMLElement).closest('.cite-tag') as HTMLElement | null
  if (!target) return
  const idx = Number(target.dataset.cite)
  const cite = props.message.citations.find((c) => c.index === idx)
  if (cite) emit('open-citation', cite)
}
</script>

<template>
  <div class="row" :class="{ user: isUser }">
    <div class="bubble" :class="{ user: isUser }">
      <div v-if="isUser" class="plain">{{ message.content }}</div>
      <template v-else>
        <div
          class="markdown-body"
          :class="{ 'stream-cursor': streaming }"
          v-html="html"
          @click="onBodyClick"
        />
        <div v-if="!message.content && streaming" class="thinking">正在检索知识库…</div>
        <div v-if="message.citations.length" class="citations">
          <div class="cite-title">引用片段（{{ message.citations.length }}）</div>
          <div class="cite-grid">
            <CitationCard v-for="c in message.citations" :key="c.chunk_id" :citation="c" @open="emit('open-citation', $event)" />
          </div>
        </div>
      </template>
      <div class="meta">
        <template v-if="isUser">
          <span v-if="message.status === 'pending'">发送中…</span>
          <template v-else-if="message.status === 'failed'">
            <span class="err">发送失败</span>
            <el-button link type="primary" size="small" :disabled="disabled" @click="emit('retry', message.id)">重试</el-button>
          </template>
        </template>
        <template v-else>
          <span v-if="tokens > 0" class="tokens">tokens {{ message.prompt_tokens }} + {{ message.completion_tokens }}</span>
          <span v-if="message.status === 'stopped'" class="warn">已停止</span>
          <span v-if="message.status === 'error'" class="err">生成失败</span>
          <el-button
            v-if="(message.status === 'stopped' || message.status === 'error' || message.status === 'completed') && !message.id.startsWith('local-')"
            link
            type="primary"
            size="small"
            :disabled="disabled"
            @click="emit('regenerate', message.id)"
          >
            重新生成
          </el-button>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.row {
  display: flex;
  margin-bottom: 16px;
}
.row.user {
  justify-content: flex-end;
}
.bubble {
  max-width: 78%;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 10px;
  padding: 10px 14px;
}
.bubble.user {
  background: #409eff;
  border-color: #409eff;
  color: #fff;
}
.plain {
  white-space: pre-wrap;
  line-height: 1.6;
}
.thinking {
  color: #909399;
  font-size: 13px;
}
.citations {
  margin-top: 10px;
  border-top: 1px dashed #e4e7ed;
  padding-top: 8px;
}
.cite-title {
  font-size: 12px;
  color: #909399;
  margin-bottom: 6px;
}
.cite-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}
.meta {
  margin-top: 6px;
  display: flex;
  gap: 10px;
  align-items: center;
  font-size: 12px;
  color: #909399;
  min-height: 16px;
}
.bubble.user .meta {
  color: rgba(255, 255, 255, 0.85);
  justify-content: flex-end;
}
.meta:empty {
  display: none;
}
.tokens {
  color: #a8abb2;
}
.warn {
  color: #e6a23c;
}
.err {
  color: #f56c6c;
}
</style>
