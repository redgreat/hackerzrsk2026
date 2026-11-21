<script setup lang="ts">
import { api } from '@/api'
import type { Account, AccountStatus } from '@/types'
import { ACCOUNT_STATUS } from '@/utils/labels'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'

const items = ref<Account[]>([])
const total = ref(0)
const pending = ref(0)
const page = ref(1)
const status = ref('')
const q = ref('')
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const r = await api.admin.accounts({ status: status.value, q: q.value.trim(), page: page.value, size: 20 })
    items.value = r.items
    total.value = r.total
    pending.value = r.pending
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function review(u: Account, action: 'approve' | 'reject' | 'disable' | 'enable') {
  const labels = { approve: '通过审核', reject: '驳回', disable: '停用', enable: '恢复' }
  await ElMessageBox.confirm(`确定${labels[action]} ${u.name}（${u.userid}）吗？`, '确认')
  await api.admin.reviewAccount(u.id, action)
  ElMessage.success('已处理')
  load()
}

async function toggleAdmin(u: Account) {
  const role = u.role === 'admin' ? 'user' : 'admin'
  await ElMessageBox.confirm(`确定将 ${u.name} 设为${role === 'admin' ? '管理员' : '普通员工'}吗？`, '确认')
  await api.admin.setRole(u.id, role)
  ElMessage.success('已更新')
  load()
}

async function resetPwd(u: Account) {
  const { value } = await ElMessageBox.prompt(`为 ${u.name} 设置新密码（至少 6 位）`, '重置密码', {
    inputPattern: /^.{6,64}$/,
    inputErrorMessage: '至少 6 位',
  })
  await api.admin.resetPassword(u.id, value)
  ElMessage.success('密码已重置')
}

const statusType = (s: AccountStatus) => ACCOUNT_STATUS[s]?.type ?? 'info'
const statusLabel = (s: AccountStatus) => ACCOUNT_STATUS[s]?.label ?? s
</script>

<template>
  <el-alert v-if="pending" type="warning" :closable="false" style="margin-bottom: 12px">
    有 {{ pending }} 个账号待审核
  </el-alert>
  <div style="margin-bottom: 12px; display: flex; gap: 8px">
    <el-select v-model="status" placeholder="全部状态" clearable style="width: 140px" @change="page = 1; load()">
      <el-option v-for="(v, k) in ACCOUNT_STATUS" :key="k" :label="v.label" :value="k" />
    </el-select>
    <el-input v-model="q" placeholder="工号 / 姓名 / 部门" clearable style="width: 220px" @change="page = 1; load()" />
    <el-button type="primary" @click="page = 1; load()">查询</el-button>
  </div>

  <el-table :data="items" v-loading="loading" border>
    <el-table-column prop="userid" label="工号" width="110" />
    <el-table-column prop="name" label="姓名" width="110" />
    <el-table-column prop="department" label="部门" width="110" />
    <el-table-column prop="source" label="来源" width="90" />
    <el-table-column label="状态" width="90">
      <template #default="{ row }"><el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag></template>
    </el-table-column>
    <el-table-column label="角色" width="90">
      <template #default="{ row }"><el-tag v-if="row.role === 'admin'" type="danger">管理员</el-tag><span v-else>员工</span></template>
    </el-table-column>
    <el-table-column prop="created_at" label="注册时间" width="180">
      <template #default="{ row }">{{ row.created_at?.slice(0, 16).replace('T', ' ') }}</template>
    </el-table-column>
    <el-table-column label="操作" min-width="280">
      <template #default="{ row }">
        <el-button v-if="row.status === 'pending'" type="success" size="small" @click="review(row as Account, 'approve')">通过</el-button>
        <el-button v-if="row.status === 'pending'" type="danger" size="small" @click="review(row as Account, 'reject')">驳回</el-button>
        <el-button v-if="row.status === 'active'" type="warning" size="small" @click="review(row as Account, 'disable')">停用</el-button>
        <el-button v-if="row.status === 'disabled' || row.status === 'rejected'" size="small" @click="review(row as Account, 'enable')">恢复</el-button>
        <el-button size="small" @click="toggleAdmin(row as Account)">{{ row.role === 'admin' ? '取消管理员' : '设为管理员' }}</el-button>
        <el-button v-if="row.has_password" size="small" @click="resetPwd(row as Account)">重置密码</el-button>
      </template>
    </el-table-column>
  </el-table>

  <el-pagination
    v-model:current-page="page"
    :total="total"
    :page-size="20"
    layout="total, prev, pager, next"
    style="margin-top: 12px"
    @change="load"
  />
</template>
