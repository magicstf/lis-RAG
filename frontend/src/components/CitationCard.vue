<script setup lang="ts">
import type { Citation } from '../api/types'

defineProps<{ citation: Citation; active?: boolean }>()
defineEmits<{ (e: 'open', citation: Citation): void }>()

function location(c: Citation) {
  const parts: string[] = []
  if (c.page_no != null) parts.push(`第 ${c.page_no} 页`)
  if (c.section) parts.push(c.section)
  return parts.join(' · ')
}
</script>

<template>
  <div class="card" :class="{ active }" @click="$emit('open', citation)">
    <div class="head">
      <span class="idx">[{{ citation.index }}]</span>
      <span class="name" :title="citation.document_name">{{ citation.document_name }}</span>
      <span class="score">{{ citation.score.toFixed(2) }}</span>
    </div>
    <div v-if="location(citation)" class="loc">{{ location(citation) }}</div>
    <div class="snippet">{{ citation.content }}</div>
  </div>
</template>

<style scoped>
.card {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 8px 10px;
  background: #fafafa;
  cursor: pointer;
  width: 100%;
}
.card:hover,
.card.active {
  border-color: #409eff;
  background: #f5faff;
}
.head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}
.idx {
  color: #409eff;
  font-weight: 600;
}
.name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #303133;
}
.score {
  color: #909399;
}
.loc {
  margin-top: 2px;
  font-size: 12px;
  color: #909399;
}
.snippet {
  margin-top: 4px;
  font-size: 12px;
  color: #606266;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
