<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, Promotion, VideoPause } from '@element-plus/icons-vue'
import { useChatStore } from '../stores/chat'
import type { Citation } from '../api/types'
import MessageBubble from '../components/MessageBubble.vue'
import CitationDrawer from '../components/CitationDrawer.vue'

const store = useChatStore()
const input = ref('')
const listEl = ref<HTMLElement | null>(null)
const activeCitation = ref<Citation | null>(null)

onMounted(() => store.loadConversations().catch(() => ElMessage.error('加载会话失败')))

watch(
  () => [store.messages.length, store.messages[store.messages.length - 1]?.content],
  () => nextTick(() => listEl.value?.scrollTo({ top: listEl.value.scrollHeight })),
)

watch(
  () => store.lastError,
  (e) => e && ElMessage.error(e),
)

async function send() {
  const q = input.value.trim()
  if (!q || store.generating) return
  if (q.length > 2000) {
    ElMessage.warning('问题不能超过 2000 个字符')
    return
  }
  input.value = ''
  await store.send(q)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    send()
  }
}

async function removeConversation(id: string) {
  try {
    await ElMessageBox.confirm('删除后该会话的全部消息将不可恢复。', '删除会话', { type: 'warning' })
  } catch {
    return
  }
  await store.removeConversation(id)
}
</script>

<template>
  <div class="chat">
    <aside class="sidebar">
      <el-button type="primary" :icon="Plus" class="new-btn" @click="store.createConversation()">新建会话</el-button>
      <div class="conv-list">
        <div
          v-for="c in store.conversations"
          :key="c.id"
          class="conv"
          :class="{ active: c.id === store.currentId }"
          @click="store.select(c.id)"
        >
          <span class="conv-title" :title="c.title">{{ c.title }}</span>
          <el-button link :icon="Delete" class="conv-del" @click.stop="removeConversation(c.id)" />
        </div>
      </div>
    </aside>

    <section class="main">
      <div ref="listEl" class="messages">
        <div v-if="!store.messages.length" class="empty">
          <p>先在「知识库」上传文档，再在这里用自然语言提问。</p>
          <p class="dim">回答会附带引用片段，点击 [n] 或引用卡片可查看原文。</p>
        </div>
        <MessageBubble
          v-for="m in store.messages"
          :key="m.id"
          :message="m"
          :disabled="store.generating"
          @open-citation="activeCitation = $event"
          @regenerate="store.regenerate($event)"
          @retry="store.retryUser($event)"
        />
      </div>

      <div class="composer">
        <el-input
          v-model="input"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          placeholder="输入问题，Enter 发送，Shift+Enter 换行"
          :disabled="store.generating"
          maxlength="2000"
          show-word-limit
          @keydown="onKeydown"
        />
        <el-button v-if="store.generating" type="danger" :icon="VideoPause" @click="store.stop()">停止</el-button>
        <el-button v-else type="primary" :icon="Promotion" :disabled="!input.trim()" @click="send">发送</el-button>
      </div>
    </section>

    <CitationDrawer :citation="activeCitation" @close="activeCitation = null" />
  </div>
</template>

<style scoped>
.chat {
  display: flex;
  height: 100%;
}
.sidebar {
  width: 260px;
  flex-shrink: 0;
  background: #fff;
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
  padding: 12px;
}
.new-btn {
  width: 100%;
}
.conv-list {
  margin-top: 12px;
  overflow: auto;
  flex: 1;
}
.conv {
  display: flex;
  align-items: center;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  color: #303133;
}
.conv:hover {
  background: #f5f7fa;
}
.conv.active {
  background: #ecf5ff;
  color: #409eff;
}
.conv-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
}
.conv-del {
  opacity: 0;
}
.conv:hover .conv-del {
  opacity: 1;
}
.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.messages {
  flex: 1;
  overflow: auto;
  padding: 20px 28px;
}
.empty {
  margin-top: 80px;
  text-align: center;
  color: #606266;
}
.dim {
  color: #a8abb2;
  font-size: 13px;
}
.composer {
  display: flex;
  gap: 10px;
  align-items: flex-end;
  padding: 12px 20px 16px;
  background: #fff;
  border-top: 1px solid #e4e7ed;
}
.composer :deep(.el-textarea) {
  flex: 1;
}
</style>
