<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'

const emit = defineEmits<{ (e: 'upload', file: File): void }>()

const ALLOWED = ['pdf', 'docx', 'md', 'txt']
const MAX_BYTES = 20 * 1024 * 1024
const dragging = ref(false)
const input = ref<HTMLInputElement | null>(null)

function validate(file: File): string | null {
  const ext = file.name.includes('.') ? file.name.split('.').pop()!.toLowerCase() : ''
  if (!ALLOWED.includes(ext)) return `不支持的文件类型：.${ext || '未知'}，仅支持 pdf / docx / md / txt`
  if (file.size > MAX_BYTES) return '文件超过 20MB 限制'
  if (file.size === 0) return '文件为空'
  return null
}

function handleFiles(files: FileList | null) {
  if (!files) return
  for (const file of Array.from(files)) {
    const err = validate(file)
    if (err) {
      ElMessage.error(`${file.name}：${err}`)
      continue
    }
    emit('upload', file)
  }
  if (input.value) input.value.value = ''
}

function onDrop(e: DragEvent) {
  dragging.value = false
  handleFiles(e.dataTransfer?.files ?? null)
}
</script>

<template>
  <div
    class="uploader"
    :class="{ dragging }"
    @dragover.prevent="dragging = true"
    @dragleave.prevent="dragging = false"
    @drop.prevent="onDrop"
    @click="input?.click()"
  >
    <el-icon :size="36" color="#409eff"><UploadFilled /></el-icon>
    <div class="title">拖拽文件到此处，或点击选择</div>
    <div class="hint">支持 .pdf / .docx / .md / .txt，单文件不超过 20MB；PDF 需有文本层</div>
    <input ref="input" type="file" multiple accept=".pdf,.docx,.md,.txt" hidden @change="handleFiles(($event.target as HTMLInputElement).files)" />
  </div>
</template>

<style scoped>
.uploader {
  border: 1px dashed #c0c4cc;
  border-radius: 8px;
  padding: 28px;
  text-align: center;
  background: #fff;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}
.uploader:hover,
.uploader.dragging {
  border-color: #409eff;
  background: #f5faff;
}
.title {
  margin-top: 8px;
  font-size: 15px;
}
.hint {
  margin-top: 6px;
  color: #909399;
  font-size: 12px;
}
</style>
