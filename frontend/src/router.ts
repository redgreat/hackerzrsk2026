import { createRouter, createWebHistory } from 'vue-router'
import { tokenStore } from './api/http'
import { useAuthStore } from './stores/auth'

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
    {
      path: '/admin',
      component: () => import('./layouts/AdminLayout.vue'),
      meta: { admin: true, title: '管理后台' },
      children: [
        { path: '', name: 'admin-dashboard', component: () => import('./views/admin/DashboardView.vue'), meta: { title: '数据概览 · 管理后台' } },
        { path: 'sessions', name: 'admin-sessions', component: () => import('./views/admin/SessionsView.vue'), meta: { title: '练习记录 · 管理后台' } },
        { path: 'sessions/:id', name: 'admin-session', component: () => import('./views/admin/SessionDetailView.vue'), meta: { title: '练习详情 · 管理后台' } },
        { path: 'users', name: 'admin-users', component: () => import('./views/admin/UsersView.vue'), meta: { title: '员工 · 管理后台' } },
        { path: 'usage', name: 'admin-usage', component: () => import('./views/admin/UsageView.vue'), meta: { title: '模型用量 · 管理后台' } },
        { path: 'scenarios', name: 'admin-scenarios', component: () => import('./views/admin/ScenariosView.vue'), meta: { title: '场景配置 · 管理后台' } },
        { path: 'knowledge', name: 'admin-knowledge', component: () => import('./views/admin/KnowledgeView.vue'), meta: { title: '话术知识库 · 管理后台' } },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  if (to.meta.public) return
  if (!tokenStore.get()) return { name: 'login', query: { redirect: to.fullPath } }
  if (to.matched.some((r) => r.meta.admin)) {
    const auth = useAuthStore()
    await auth.loadMe()
    if (!auth.user?.is_admin) return { name: 'home' }
  }
})

router.afterEach((to) => {
  document.title = (to.meta.title as string | undefined) ?? 'AI 客户陪练'
})

export default router
