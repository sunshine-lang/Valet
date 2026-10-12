import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: () => import('@/views/ChatView.vue'), meta: { title: '新对话' } },
    { path: '/c/:id', name: 'chat', component: () => import('@/views/ChatView.vue'), meta: { title: '对话' } },
    { path: '/skills', name: 'skills', component: () => import('@/views/SkillsView.vue'), meta: { title: '技能' } },
    { path: '/knowledge', name: 'knowledge', component: () => import('@/views/PlaceholderView.vue'), meta: { title: '知识库' } },
    { path: '/schedules', name: 'schedules', component: () => import('@/views/SchedulesView.vue'), meta: { title: '定时任务' } },
    { path: '/agent', redirect: '/settings/model' },
    { path: '/tools', redirect: '/settings/tools' },
    { path: '/settings', redirect: '/settings/model' },
    { path: '/settings/runs/:id', name: 'settings-run', component: () => import('@/views/SettingsView.vue'), meta: { title: '运行详情' } },
    { path: '/settings/:section', name: 'settings', component: () => import('@/views/SettingsView.vue'), meta: { title: '设置' } },
    { path: '/runs', redirect: '/settings/runs' },
    { path: '/runs/:id', redirect: (to) => `/settings/runs/${to.params.id}` },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
