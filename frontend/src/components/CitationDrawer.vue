<script setup lang="ts">
import { ref, watch } from 'vue'
import { documentsApi } from '../api'
import { ApiError } from '../api/http'
import type { ChunkDetail, Citation } from '../api/types'

const props = defineProps<{ citation: Citation | null }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const visible = ref(false)
const loading = ref(false)
const detail = ref<ChunkDetail | null>(null)
const error = ref<string | null>(null)

watch(
  () => props.citation,
  async (c) => {
    if (!c) {
      visible.value = false
      return
    }
    visible.value = true
    loading.value = true
    error.value = null
    detail.value = null
    try {
      detail.value = await documentsApi.chunk(c.document_id, c.chunk_id)
    } catch (e) {
      error.value = e instanceof ApiError ? e.message : '加载片段失败'
    } finally {
      loading.value = false
    }
  },
)
</script>

<template>
  <el-drawer v-model="visible" size="480px" :title="citation ? `引用 [${citation.index}]` : '引用'" @closed="emit('close')">
    <template v-if="citation">
      <el-descriptions :column="1" size="small" border>
        <el-descriptions-item label="文档">{{ citation.document_name }}</el-descriptions-item>
        <el-descriptions-item label="页码">{{ citation.page_no ?? '无' }}</el-descriptions-item>
        <el-descriptions-item label="章节">{{ citation.section || '无' }}</el-descriptions-item>
        <el-descriptions-item label="相关度">{{ citation.score.toFixed(4) }}</el-descriptions-item>
        <el-descriptions-item v-if="detail" label="位置">
          第 {{ detail.seq + 1 }} 段 · 字符 {{ detail.char_start }}–{{ detail.char_end }}
        </el-descriptions-item>
      </el-descriptions>
      <div class="body">
        <el-skeleton v-if="loading" :rows="6" animated />
        <el-alert v-else-if="error" type="error" :closable="false" :title="error" />
        <div v-else class="highlight-chunk">{{ detail?.content ?? citation.content }}</div>
      </div>
    </template>
  </el-drawer>
</template>

<style scoped>
.body {
  margin-top: 16px;
}
</style>
