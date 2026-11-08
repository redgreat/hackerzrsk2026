import { createRouter, createWebHistory } from 'vue-router'
import { tokenStore } from './api/http'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('./views/LoginView.vue'), meta: { public: true } },
    { path: '/', name: 'home', component: () => import('./views/HomeView.vue'), meta: { tab: true, title: 'AI 客户陪练' } },
    { path: '/scenario/:id', name: 'scenario', component: () => import('./views/ScenarioView.vue'), meta: { title: '场景说明' } },
    { path: '/practice/:id', name: 'practice', component: () => import('./views/PracticeView.vue'), meta: { title: '对练中' } },
    { path: '/report/:id', name: 'report', component: () => import('./views/ReportView.vue'), meta: { title: '评分报告' } },
    { path: '/history', name: 'history', component: () => import('./views/HistoryView.vue'), meta: { tab: true, title: '我的练习' } },
    { path: '/overview', name: 'overview', component: () => import('./views/OverviewView.vue'), meta: { title: '效果与成本' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach((to) => {
  if (!to.meta.public && !tokenStore.get()) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
})

router.afterEach((to) => {
  document.title = (to.meta.title as string | undefined) ?? 'AI 客户陪练'
})

export default router
