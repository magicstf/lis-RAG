<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useEvalStore } from '../stores/eval'
import { useDocumentsStore } from '../stores/documents'
import { ApiError } from '../api/http'
import type { EvalRun } from '../api/types'
import { formatTime } from '../utils/markdown'

const store = useEvalStore()
const docs = useDocumentsStore()

const form = reactive({ chunk_size: 500, chunk_overlap: 50, use_hybrid: true, use_rerank: false })
const compareId = ref<string | null>(null)

onMounted(async () => {
  await Promise.allSettled([store.loadRuns(), store.loadUsage(), docs.fetchList()])
  docs.stopPolling()
  const ready = docs.items.find((d) => d.status === 'ready')
  if (ready) {
    form.chunk_size = ready.chunk_size
    form.chunk_overlap = ready.chunk_overlap
  }
})

const compare = computed<EvalRun | null>(() => store.runs.find((r) => r.id === compareId.value) ?? null)
const diff = computed(() => {
  if (!store.latest || !compare.value) return null
  return {
    recall: store.latest.recall_at_k - compare.value.recall_at_k,
    mrr: store.latest.mrr - compare.value.mrr,
    refusal: store.latest.refusal_rate - compare.value.refusal_rate,
  }
})

const usageTotal = computed(() =>
  store.usage.reduce(
    (acc, d) => ({
      prompt: acc.prompt + d.prompt_tokens,
      completion: acc.completion + d.completion_tokens,
      llm: acc.llm + d.llm_calls,
      embedding: acc.embedding + d.embedding_calls,
    }),
    { prompt: 0, completion: 0, llm: 0, embedding: 0 },
  ),
)

function fmtDiff(v: number) {
  const s = (v * 100).toFixed(1)
  return v > 0 ? `+${s}` : s
}

async function run() {
  if (form.chunk_overlap >= form.chunk_size) {
    ElMessage.error('overlap 必须小于 chunk_size')
    return
  }
  const readyDocs = docs.items.filter((d) => d.status === 'ready')
  if (!readyDocs.length) {
    ElMessage.warning('没有就绪的文档，请先在知识库上传')
    return
  }
  const mismatch = readyDocs.some((d) => d.chunk_size !== form.chunk_size || d.chunk_overlap !== form.chunk_overlap)
  if (mismatch) {
    try {
      await ElMessageBox.confirm('将按新的切分参数重建当前知识库索引，现有向量会被覆盖。', '重建索引', {
        type: 'warning',
        confirmButtonText: '继续运行',
        cancelButtonText: '取消',
      })
    } catch {
      return
    }
  }
  try {
    const previous = store.latest
    const result = await store.run({ ...form })
    if (previous) compareId.value = previous.id
    ElMessage.success(`评测完成：Recall@${result.config.k} = ${result.recall_at_k}`)
    await Promise.allSettled([store.loadUsage(), docs.fetchList()])
    docs.stopPolling()
  } catch (e) {
    ElMessage.error(e instanceof ApiError ? e.message : '评测运行失败')
  }
}

function runLabel(r: EvalRun) {
  const c = r.config
  return `${formatTime(r.created_at)} · ${c.chunk_size}/${c.chunk_overlap} · ${c.use_hybrid ? '混合' : '向量'}${c.use_rerank ? '+rerank' : ''} · R@${c.k}=${r.recall_at_k}`
}
</script>

<template>
  <div class="page">
    <el-card shadow="never">
      <el-form inline>
        <el-form-item label="chunk_size">
          <el-input-number v-model="form.chunk_size" :min="50" :max="5000" :step="50" />
        </el-form-item>
        <el-form-item label="overlap">
          <el-input-number v-model="form.chunk_overlap" :min="0" :max="2000" :step="10" />
        </el-form-item>
        <el-form-item label="混合检索">
          <el-switch v-model="form.use_hybrid" />
        </el-form-item>
        <el-form-item label="rerank">
          <el-switch v-model="form.use_rerank" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="store.running" @click="run">{{ store.running ? '运行中…' : '运行评测' }}</el-button>
        </el-form-item>
      </el-form>
      <div class="dim">当前就绪文档 {{ docs.readyCount }} 份。切分参数与现有索引不一致时，运行前会先重建索引。</div>
    </el-card>

    <template v-if="store.latest">
      <div class="metrics">
        <el-card shadow="never" class="metric">
          <div class="label">Recall@{{ store.latest.config.k }}</div>
          <div class="value">{{ (store.latest.recall_at_k * 100).toFixed(1) }}%</div>
          <div v-if="diff" class="diff" :class="{ up: diff.recall > 0, down: diff.recall < 0 }">{{ fmtDiff(diff.recall) }} pt</div>
        </el-card>
        <el-card shadow="never" class="metric">
          <div class="label">MRR</div>
          <div class="value">{{ store.latest.mrr.toFixed(3) }}</div>
          <div v-if="diff" class="diff" :class="{ up: diff.mrr > 0, down: diff.mrr < 0 }">{{ fmtDiff(diff.mrr) }} pt</div>
        </el-card>
        <el-card shadow="never" class="metric">
          <div class="label">拒答率</div>
          <div class="value">{{ (store.latest.refusal_rate * 100).toFixed(0) }}%</div>
          <div v-if="diff" class="diff" :class="{ up: diff.refusal > 0, down: diff.refusal < 0 }">{{ fmtDiff(diff.refusal) }} pt</div>
        </el-card>
        <el-card shadow="never" class="metric compare">
          <div class="label">对比历史运行</div>
          <el-select v-model="compareId" clearable placeholder="选择一次历史运行" style="width: 100%">
            <el-option v-for="r in store.runs.filter((x) => x.id !== store.latest?.id)" :key="r.id" :value="r.id" :label="runLabel(r)" />
          </el-select>
          <div class="dim">
            本次：{{ store.latest.config.chunk_size }}/{{ store.latest.config.chunk_overlap }} ·
            {{ store.latest.config.use_hybrid ? '混合' : '向量' }}{{ store.latest.config.use_rerank ? '+rerank' : '' }}
          </div>
        </el-card>
      </div>

      <el-table :data="store.latest.detail" class="table" size="small">
        <el-table-column prop="id" label="编号" width="70" />
        <el-table-column label="类型" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.type === 'refusal' ? 'warning' : 'info'" effect="plain">{{ row.type === 'refusal' ? '拒答' : '可答' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="question" label="问题" min-width="240" show-overflow-tooltip />
        <el-table-column label="通过" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.hit ? 'success' : 'danger'">{{ row.hit ? '通过' : '未通过' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="rank" width="70">
          <template #default="{ row }">{{ row.type === 'refusal' ? '-' : row.rank || '-' }}</template>
        </el-table-column>
        <el-table-column label="门控分" width="90">
          <template #default="{ row }">{{ row.gate_score.toFixed(3) }}</template>
        </el-table-column>
        <el-table-column label="答案要点" min-width="260">
          <template #default="{ row }">
            <div v-for="(p, i) in row.answer_points" :key="i" class="point">· {{ p }}</div>
          </template>
        </el-table-column>
      </el-table>
    </template>
    <el-empty v-else description="还没有评测记录，设置参数后点击「运行评测」" />

    <el-card shadow="never" class="usage">
      <div class="label">近 7 日用量</div>
      <div class="usage-row">
        <span>LLM 调用 {{ usageTotal.llm }} 次</span>
        <span>prompt tokens {{ usageTotal.prompt }}</span>
        <span>completion tokens {{ usageTotal.completion }}</span>
        <span>Embedding 调用 {{ usageTotal.embedding }} 次</span>
      </div>
      <el-table :data="store.usage" size="small" class="table-compact">
        <el-table-column prop="date" label="日期 (UTC)" width="120" />
        <el-table-column prop="llm_calls" label="LLM 调用" width="100" />
        <el-table-column prop="prompt_tokens" label="prompt" width="100" />
        <el-table-column prop="completion_tokens" label="completion" width="110" />
        <el-table-column prop="embedding_calls" label="Embedding 调用" width="130" />
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.dim {
  color: #909399;
  font-size: 12px;
  margin-top: 4px;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-top: 16px;
}
.metric .label {
  color: #909399;
  font-size: 13px;
}
.metric .value {
  font-size: 28px;
  font-weight: 600;
  margin-top: 4px;
}
.diff {
  font-size: 12px;
  color: #909399;
}
.diff.up {
  color: #67c23a;
}
.diff.down {
  color: #f56c6c;
}
.table {
  margin-top: 16px;
  background: #fff;
}
.point {
  font-size: 12px;
  color: #606266;
}
.usage {
  margin-top: 16px;
}
.usage-row {
  display: flex;
  gap: 24px;
  margin: 8px 0 12px;
  font-size: 13px;
  color: #303133;
}
.table-compact {
  max-width: 600px;
}
</style>
