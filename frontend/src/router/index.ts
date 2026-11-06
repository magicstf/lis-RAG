import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/chat' },
    { path: '/knowledge', name: 'knowledge', component: () => import('../views/KnowledgeBase.vue') },
    { path: '/chat', name: 'chat', component: () => import('../views/Chat.vue') },
    { path: '/eval', name: 'eval', component: () => import('../views/EvalPanel.vue') },
  ],
})

export default router
