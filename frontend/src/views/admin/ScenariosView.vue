<script setup lang="ts">
import { api } from '@/api'
import type { AdminScenario } from '@/types'
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'

const list = ref<AdminScenario[]>([])

onMounted(async () => {
  try {
    list.value = await api.admin.scenarios()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
})
</script>

<template>
  <div>
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="场景与评分表由 scenarios/*.yaml、scenarios/rubrics/*.yaml 维护（只读展示）。修改后重启服务生效，并执行 python -m app.cli check-scenarios 校验。"
      class="tip"
    />
    <el-card v-for="s in list" :key="s.id" shadow="never" class="block">
      <template #header>
        <div class="head">
          <span><b>{{ s.id }}</b> {{ s.name }}</span>
          <span class="muted">{{ s.department.join('、') }} · 难度 {{ s.difficulty }} · 最多 {{ s.max_turns }} 轮 · 评分表 {{ s.rubric.name }}</span>
        </div>
      </template>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="客户">{{ s.persona.name }} · {{ s.persona.role }}</el-descriptions-item>
        <el-descriptions-item label="性格">{{ s.persona.personality }}</el-descriptions-item>
        <el-descriptions-item label="背景" :span="2">{{ s.background }}</el-descriptions-item>
        <el-descriptions-item label="员工目标" :span="2">{{ s.goal }}</el-descriptions-item>
        <el-descriptions-item label="隐藏需求" :span="2">
          <el-tag v-for="n in s.persona.hidden_needs" :key="n" class="tag" effect="plain">{{ n }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="状态阈值" :span="2">
          初始信任 {{ s.state_rules.initial_trust }} · 成交线 {{ s.state_rules.deal_threshold }} ·
          挂断线 {{ s.state_rules.hangup_threshold }} · 最少 {{ s.state_rules.min_turns_to_deal }} 轮才可成交
        </el-descriptions-item>
      </el-descriptions>

      <div class="sub">异议（关键异议未化解不能成交）</div>
      <el-table :data="s.persona.objections" size="small">
        <el-table-column prop="id" label="ID" width="90" />
        <el-table-column prop="text" label="异议" min-width="200" />
        <el-table-column label="关键" width="70">
          <template #default="{ row }"><el-tag :type="row.key ? 'danger' : 'info'" size="small">{{ row.key ? '是' : '否' }}</el-tag></template>
        </el-table-column>
        <el-table-column label="化解要点" min-width="220">
          <template #default="{ row }">{{ row.resolve_hints.join('、') }}</template>
        </el-table-column>
      </el-table>

      <div class="sub">评分维度</div>
      <el-table :data="s.rubric.dimensions" size="small">
        <el-table-column prop="name" label="维度" width="160" />
        <el-table-column prop="weight" label="权重" width="80" />
        <el-table-column prop="good" label="5 分标准" min-width="180" />
        <el-table-column prop="bad" label="1 分标准" min-width="180" />
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.tip {
  margin-bottom: 16px;
}
.block {
  margin-bottom: 16px;
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.muted {
  color: #86909c;
  font-size: 12px;
}
.sub {
  margin: 16px 0 8px;
  font-weight: 600;
}
.tag {
  margin-right: 6px;
}
</style>
