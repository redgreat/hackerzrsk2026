<script setup lang="ts">
import { api } from '@/api'
import type { AdminUser } from '@/types'
import { formatTime, scoreColor } from '@/utils/labels'
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const q = ref('')
const page = ref(1)
const size = 20
const loading = ref(false)
const rows = ref<AdminUser[]>([])
const total = ref(0)

async function load() {
  loading.value = true
  try {
    const res = await api.admin.users({ q: q.value.trim(), page: page.value, size })
    rows.value = res.items
    total.value = res.total
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

function search() {
  page.value = 1
  load()
}

onMounted(load)
</script>

<template>
  <el-card shadow="never">
    <div class="toolbar">
      <el-input v-model="q" placeholder="搜索工号 / 姓名 / 部门" clearable style="width: 280px" @keyup.enter="search" @clear="search" />
      <el-button type="primary" @click="search">搜索</el-button>
      <span class="muted">点击行可查看该员工的练习记录</span>
    </div>

    <el-table
      v-loading="loading"
      :data="rows"
      stripe
      style="cursor: pointer"
      @row-click="(r: AdminUser) => router.push({ path: '/admin/sessions', query: { user_id: r.id } })"
    >
      <el-table-column prop="userid" label="工号" width="120" />
      <el-table-column prop="name" label="姓名" width="120" />
      <el-table-column prop="department" label="部门" min-width="120" />
      <el-table-column prop="source" label="来源" width="90" />
      <el-table-column prop="sessions" label="练习次数" width="100" />
      <el-table-column label="平均分" width="100">
        <template #default="{ row }">
          <b :style="{ color: scoreColor(row.avg_score) }">{{ row.avg_score ?? '-' }}</b>
        </template>
      </el-table-column>
      <el-table-column label="累计成本（元）" width="130">
        <template #default="{ row }">{{ row.cost_yuan.toFixed(3) }}</template>
      </el-table-column>
      <el-table-column label="最近练习" width="130">
        <template #default="{ row }">{{ formatTime(row.last_practice_at) }}</template>
      </el-table-column>
      <el-table-column label="最近登录" width="130">
        <template #default="{ row }">{{ formatTime(row.last_login_at) }}</template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="page"
      :page-size="size"
      :total="total"
      layout="total, prev, pager, next"
      class="pager"
      @current-change="load"
    />
  </el-card>
</template>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.muted {
  color: #86909c;
  font-size: 12px;
}
.pager {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
