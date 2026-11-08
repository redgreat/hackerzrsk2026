<script setup lang="ts">
import { api } from '@/api'
import type { AdminScenario, AdminSession, AdminUser, Outcome } from '@/types'
import { OUTCOME_EL_TAG, OUTCOME_LABEL, formatTime, scoreColor } from '@/utils/labels'
import { ElMessage } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const rows = ref<AdminSession[]>([])
const total = ref(0)
const scenarios = ref<AdminScenario[]>([])
const userOptions = ref<AdminUser[]>([])
const filter = reactive({
  user_id: route.query.user_id ? Number(route.query.user_id) : (undefined as number | undefined),
  scenario_id: undefined as string | undefined,
  status: undefined as Outcome | undefined,
  page: 1,
  size: 20,
})

async function load() {
  loading.value = true
  try {
    const page = await api.admin.sessions({ ...filter })
    rows.value = page.items
    total.value = page.total
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

async function searchUsers(q: string) {
  userOptions.value = (await api.admin.users({ q, size: 20 })).items
}

function reset() {
  filter.user_id = undefined
  filter.scenario_id = undefined
  filter.status = undefined
  filter.page = 1
  load()
}

onMounted(async () => {
  scenarios.value = await api.admin.scenarios()
  if (filter.user_id) await searchUsers('')
  load()
})
</script>

<template>
  <el-card shadow="never">
    <el-form inline class="filters" @submit.prevent>
      <el-form-item label="员工">
        <el-select
          v-model="filter.user_id"
          filterable
          remote
          clearable
          reserve-keyword
          placeholder="工号 / 姓名"
          :remote-method="searchUsers"
          style="width: 220px"
          @change="() => { filter.page = 1; load() }"
          @visible-change="(v: boolean) => v && searchUsers('')"
        >
          <el-option v-for="u in userOptions" :key="u.id" :label="`${u.name}（${u.userid}）`" :value="u.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="场景">
        <el-select v-model="filter.scenario_id" clearable placeholder="全部" style="width: 180px" @change="() => { filter.page = 1; load() }">
          <el-option v-for="s in scenarios" :key="s.id" :label="s.name" :value="s.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="结果">
        <el-select v-model="filter.status" clearable placeholder="全部" style="width: 140px" @change="() => { filter.page = 1; load() }">
          <el-option v-for="(label, value) in OUTCOME_LABEL" :key="value" :label="label" :value="value" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button @click="reset">重置</el-button>
      </el-form-item>
    </el-form>

    <el-table v-loading="loading" :data="rows" stripe @row-click="(r: AdminSession) => router.push(`/admin/sessions/${r.id}`)" style="cursor: pointer">
      <el-table-column label="开始时间" width="130">
        <template #default="{ row }">{{ formatTime(row.started_at) }}</template>
      </el-table-column>
      <el-table-column label="员工" min-width="130">
        <template #default="{ row }">{{ row.user_name }}（{{ row.userid }}）</template>
      </el-table-column>
      <el-table-column prop="department" label="部门" width="90" />
      <el-table-column prop="scenario_name" label="场景" min-width="150" />
      <el-table-column label="结果" width="110">
        <template #default="{ row }"><el-tag :type="OUTCOME_EL_TAG[row.status as Outcome]" size="small">{{ OUTCOME_LABEL[row.status as Outcome] }}</el-tag></template>
      </el-table-column>
      <el-table-column label="得分" width="80">
        <template #default="{ row }"><b :style="{ color: scoreColor(row.total_score) }">{{ row.total_score ?? '-' }}</b></template>
      </el-table-column>
      <el-table-column prop="turns" label="轮数" width="70" />
      <el-table-column prop="hints_used" label="求助" width="70" />
      <el-table-column label="成本（元）" width="100">
        <template #default="{ row }">{{ row.cost_yuan.toFixed(3) }}</template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="filter.page"
      :page-size="filter.size"
      :total="total"
      layout="total, prev, pager, next"
      class="pager"
      @current-change="load"
    />
  </el-card>
</template>

<style scoped>
.filters {
  margin-bottom: 8px;
}
.pager {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
