<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { useDocumentsStore } from '../stores/documents'
import { ApiError } from '../api/http'
import type { DocumentItem } from '../api/types'
import DocUploader from '../components/DocUploader.vue'
import { formatBytes, formatTime } from '../utils/markdown'

const store = useDocumentsStore()
const uploading = ref(0)

const reindexDialog = reactive({ visible: false, doc: null as DocumentItem | null, chunk_size: 500, chunk_overlap: 50 })

onMounted(() => store.fetchList().catch((e) => ElMessage.error(errMsg(e))))
onUnmounted(() => store.stopPolling())

function errMsg(e: unknown) {
  return e instanceof ApiError ? e.message : '请求失败'
}

async function onUpload(file: File) {
  uploading.value++
  try {
    const doc = await store.upload(file)
    if (doc.status === 'failed') ElMessage.warning(`${file.name}：${doc.error_msg}`)
    else ElMessage.success(`${file.name} 已上传，正在处理`)
  } catch (e) {
    ElMessage.error(`${file.name}：${errMsg(e)}`)
  } finally {
    uploading.value--
  }
}

async function onDelete(doc: DocumentItem) {
  try {
    await ElMessageBox.confirm(`将删除「${doc.filename}」及其全部向量与文件，且不可恢复。`, '确认删除', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await store.remove(doc.id)
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

function openReindex(doc: DocumentItem) {
  reindexDialog.doc = doc
  reindexDialog.chunk_size = doc.chunk_size
  reindexDialog.chunk_overlap = doc.chunk_overlap
  reindexDialog.visible = true
}

async function confirmReindex() {
  if (!reindexDialog.doc) return
  if (reindexDialog.chunk_overlap >= reindexDialog.chunk_size) {
    ElMessage.error('overlap 必须小于 chunk_size')
    return
  }
  try {
    await store.reindex(reindexDialog.doc.id, {
      chunk_size: reindexDialog.chunk_size,
      chunk_overlap: reindexDialog.chunk_overlap,
    })
    ElMessage.success('已开始重建索引')
    reindexDialog.visible = false
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

const statusMap: Record<string, { label: string; type: 'info' | 'success' | 'danger' }> = {
  processing: { label: '处理中', type: 'info' },
  ready: { label: '就绪', type: 'success' },
  failed: { label: '失败', type: 'danger' },
}
</script>

<template>
  <div class="page">
    <DocUploader @upload="onUpload" />
    <div v-if="uploading" class="uploading">正在上传 {{ uploading }} 个文件…</div>

    <el-table :data="store.items" v-loading="store.loading && !store.items.length" class="table" empty-text="还没有文档，先上传一份再开始提问">
      <el-table-column prop="filename" label="名称" min-width="220" show-overflow-tooltip />
      <el-table-column prop="file_type" label="类型" width="80">
        <template #default="{ row }">{{ row.file_type.toUpperCase() }}</template>
      </el-table-column>
      <el-table-column label="大小" width="100">
        <template #default="{ row }">{{ formatBytes(row.file_size) }}</template>
      </el-table-column>
      <el-table-column label="chunk 数" width="100">
        <template #default="{ row }">{{ row.chunk_count }} <span class="dim">({{ row.chunk_size }}/{{ row.chunk_overlap }})</span></template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tooltip :disabled="row.status !== 'failed'" :content="row.error_msg || '处理失败'" placement="top">
            <el-tag :type="statusMap[row.status].type" size="small" effect="light" disable-transitions>
              <el-icon v-if="row.status === 'processing'" class="is-loading" style="margin-right: 4px"><Loading /></el-icon>
              {{ statusMap[row.status].label }}
            </el-tag>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="上传时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="170" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" :disabled="row.status === 'processing'" @click="openReindex(row)">重建索引</el-button>
          <el-button link type="danger" size="small" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="reindexDialog.visible" title="重建索引" width="420px">
      <el-form label-width="110px">
        <el-form-item label="chunk_size">
          <el-input-number v-model="reindexDialog.chunk_size" :min="50" :max="5000" :step="50" />
        </el-form-item>
        <el-form-item label="chunk_overlap">
          <el-input-number v-model="reindexDialog.chunk_overlap" :min="0" :max="2000" :step="10" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reindexDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="confirmReindex">开始重建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.uploading {
  margin-top: 8px;
  color: #409eff;
  font-size: 13px;
}
.table {
  margin-top: 16px;
}
.dim {
  color: #a8abb2;
  font-size: 12px;
}
</style>
