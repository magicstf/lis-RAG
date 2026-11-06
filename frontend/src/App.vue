<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()
const nav = [
  { path: '/knowledge', label: '知识库' },
  { path: '/chat', label: '对话' },
  { path: '/eval', label: '评测' },
]
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <div class="brand">知识库智能问答</div>
      <nav class="nav">
        <RouterLink v-for="item in nav" :key="item.path" :to="item.path" :class="{ active: route.path === item.path }">
          {{ item.label }}
        </RouterLink>
      </nav>
    </header>
    <main class="content">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.topbar {
  height: 52px;
  display: flex;
  align-items: center;
  padding: 0 24px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  flex-shrink: 0;
}
.brand {
  font-weight: 600;
  font-size: 16px;
  margin-right: 32px;
}
.nav a {
  margin-right: 20px;
  color: #606266;
  text-decoration: none;
  padding: 6px 0;
  border-bottom: 2px solid transparent;
}
.nav a.active {
  color: #409eff;
  border-bottom-color: #409eff;
}
.content {
  flex: 1;
  min-height: 0;
}
</style>
