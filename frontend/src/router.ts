import { createRouter, createWebHistory } from 'vue-router'
import { tokenStore } from './api/http'
import { useAuthStore } from './stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('./views/LoginView.vue'), meta: { public: true } },
    { path: '/', name: 'home', component: () => import('./views/HomeView.vue'), meta: { tab: true, title: 'AI 客户话术陪练' } },
    { path: '/intro', name: 'project-intro', component: () => import('./views/ProjectIntroView.vue'), meta: { title: '项目介绍 · AI 客户话术陪练' } },
    { path: '/scenario/:id', name: 'scenario', component: () => import('./views/ScenarioView.vue'), meta: { title: '场景说明' } },
    { path: '/practice/:id', name: 'practice', component: () => import('./views/PracticeView.vue'), meta: { title: '对练中' } },
    { path: '/report/:id', name: 'report', component: () => import('./views/ReportView.vue'), meta: { title: '评分报告' } },
    { path: '/my', name: 'my', component: () => import('./views/MyView.vue'), meta: { tab: true, title: '我的' } },
    { path: '/history', name: 'history', component: () => import('./views/HistoryView.vue'), meta: { title: '练习记录' } },
    { path: '/my/exams', name: 'exam-history', component: () => import('./views/ExamHistoryView.vue'), meta: { title: '考试记录' } },
    { path: '/recordings', component: () => import('./views/RecordingsView.vue'), meta: { tab: true, title: '录音学习' } },
    { path: '/recordings/:id', component: () => import('./views/RecordingLearningView.vue'), meta: { title: '录音详情' } },
    { path: '/exams', name: 'exams', component: () => import('./views/ExamsView.vue'), meta: { tab: true, title: '考试与自测' } },
    { path: '/attempt/:id', name: 'attempt', component: () => import('./views/AttemptView.vue'), meta: { title: '答题' } },
    { path: '/overview', name: 'overview', component: () => import('./views/OverviewView.vue'), meta: { title: '效果与成本' } },
    {
      path: '/admin',
      component: () => import('./layouts/AdminLayout.vue'),
      meta: { admin: true, title: '管理后台' },
      children: [
        { path: '', name: 'admin-dashboard', component: () => import('./views/admin/DashboardView.vue'), meta: { title: '数据概览 · 管理后台', guide: '按时间查看练习次数和平均分，结合分场景表现和模型费用了解培训情况。' } },
        { path: 'sessions', name: 'admin-sessions', component: () => import('./views/admin/SessionsView.vue'), meta: { title: '练习记录 · 管理后台', guide: '按员工、场景或结果筛选练习，点「详情」查看原对话和 AI 评分。' } },
        { path: 'sessions/:id', name: 'admin-session', component: () => import('./views/admin/SessionDetailView.vue'), meta: { title: '练习详情 · 管理后台', guide: '对照完整对话、分项判分和教练点评，了解本次练习的得分依据。' } },
        { path: 'users', name: 'admin-users', component: () => import('./views/admin/UsersView.vue'), meta: { title: '员工 · 管理后台', guide: '按姓名或工号查找员工，查看练习次数、平均分和模型费用。账号审批在「账号审核」办理。' } },
        { path: 'usage', name: 'admin-usage', component: () => import('./views/admin/UsageView.vue'), meta: { title: '模型用量 · 管理后台', guide: '按调用用途筛选，查看模型、输入输出 Token、耗时和费用明细。' } },
        { path: 'rubric', name: 'admin-rubric', component: () => import('./views/admin/RubricView.vue'), meta: { title: '评分标准 · 管理后台', guide: '编辑评分维度、权重、求助扣分和合规红线。发布后对新练习和新答卷生效，进行中的会话按原版本评分。' } },
        { path: 'accounts', name: 'admin-accounts', component: () => import('./views/admin/AccountsView.vue'), meta: { title: '账号审核 · 管理后台', guide: '筛选待审核的注册申请，核对员工信息后处理。也可在这里管理已有账号的状态和角色。' } },
        { path: 'recordings', name: 'admin-recordings', component: () => import('./views/admin/RecordingsAdminView.vue'), meta: { title: '优秀录音 · 管理后台', guide: '从 DBMCP 导入有 AI 转写的优质录音，打开录音详情后可生成、审核并发布关联练习。' } },
        { path: 'recordings/:id', name: 'admin-recording', component: () => import('./views/admin/RecordingAdminDetailView.vue'), meta: { title: '录音详情 · 管理后台', guide: '先核对转写，再生成练习并审核。发布录音会开放可用练习，撤销发布会同步下架。' } },
        { path: 'exams', name: 'admin-exams', component: () => import('./views/admin/ExamAttemptsView.vue'), meta: { title: '考试管理 · 管理后台', guide: '在「考试题库」生成和审核合规题，在「考试成绩」查看员工答卷。' } },
        { path: 'exams/:id', name: 'admin-exam', component: () => import('./views/admin/ExamAttemptDetailView.vue'), meta: { title: '答卷详情 · 管理后台', guide: '查看这次考试抽到的题目和员工答案，交卷后可核对各部分得分与解析。' } },
        { path: 'knowledge', name: 'admin-knowledge', component: () => import('./views/admin/KnowledgeView.vue'), meta: { title: '话术知识库 · 管理后台', guide: '按分类管理脱敏话术。启用的话术供 AI 教练在求助和点评时参考，可用 JSON 跨环境迁移。' } },
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
  document.title = (to.meta.title as string | undefined) ?? 'AI 客户话术陪练'
})

export default router
