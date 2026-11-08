<script setup lang="ts">
import { api } from '@/api'
import ScoreRadar from '@/components/ScoreRadar.vue'
import type { AdminSessionDetail, Outcome } from '@/types'
import { OUTCOME_EL_TAG, OUTCOME_LABEL, PURPOSE_LABEL, formatTime, scoreColor } from '@/utils/labels'
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const data = ref<AdminSessionDetail | null>(null)
const ROLE: Record<string, string> = { user: '员工', customer: '客户', hint: '教练提示' }

onMounted(async () => {
  try {
    data.value = await api.admin.session(route.params.id as string)
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
})

const sumUsage = (k: 'prompt_tokens' | 'completion_tokens' | 'cost_yuan') =>
  (data.value?.usage ?? []).reduce((s, r) => s + r[k], 0)
</script>

<template>
  <div v-if="data">
    <el-page-header @back="router.push('/admin/sessions')">
      <template #content>练习详情 · {{ data.scenario_name }}</template>
    </el-page-header>

    <el-card shadow="never" class="block">
      <el-descriptions :column="4" border size="small">
        <el-descriptions-item label="员工">{{ data.user.name }}（{{ data.user.userid }}）</el-descriptions-item>
        <el-descriptions-item label="部门">{{ data.user.department || '-' }}</el-descriptions-item>
        <el-descriptions-item label="结果">
          <el-tag :type="OUTCOME_EL_TAG[data.status as Outcome]" size="small">{{ OUTCOME_LABEL[data.status as Outcome] }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="得分">
          <b :style="{ color: scoreColor(data.total_score) }">{{ data.total_score ?? '-' }}</b>
        </el-descriptions-item>
        <el-descriptions-item label="开始">{{ formatTime(data.started_at) }}</el-descriptions-item>
        <el-descriptions-item label="结束">{{ formatTime(data.ended_at) }}</el-descriptions-item>
        <el-descriptions-item label="轮数 / 求助">{{ data.turns }} / {{ data.hints_used }}</el-descriptions-item>
        <el-descriptions-item label="最终信任值">{{ data.final_trust ?? '-' }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-row :gutter="16">
      <el-col :span="10">
        <el-card v-if="data.report" shadow="never" class="block">
          <template #header>评分报告</template>
          <p class="summary">{{ data.report.summary }}</p>
          <ScoreRadar :dimensions="data.report.dimension_scores" />
          <el-table :data="data.report.dimension_scores" size="small">
            <el-table-column prop="name" label="维度" min-width="110" />
            <el-table-column prop="score" label="分" width="60" />
            <el-table-column prop="comment" label="点评" min-width="180" />
          </el-table>
          <div class="sub">亮点</div>
          <el-tag v-for="h in data.report.highlights" :key="h" type="success" effect="plain" class="tag">{{ h }}</el-tag>
          <div class="sub">改进</div>
          <el-tag v-for="i in data.report.improvements" :key="i" type="warning" effect="plain" class="tag">{{ i }}</el-tag>
        </el-card>
        <el-empty v-else description="报告尚未生成" />

        <el-card shadow="never" class="block">
          <template #header>模型调用（{{ data.usage.length }} 次）</template>
          <el-table :data="data.usage" size="small">
            <el-table-column label="用途" min-width="90">
              <template #default="{ row }">{{ PURPOSE_LABEL[row.purpose] ?? row.purpose }}</template>
            </el-table-column>
            <el-table-column label="Token（入/出）" min-width="130">
              <template #default="{ row }">{{ row.prompt_tokens }} / {{ row.completion_tokens }}</template>
            </el-table-column>
            <el-table-column label="费用（元）" width="110">
              <template #default="{ row }">{{ row.cost_yuan.toFixed(4) }}</template>
            </el-table-column>
          </el-table>
          <p class="note">
            合计 Token {{ sumUsage('prompt_tokens') + sumUsage('completion_tokens') }}，费用 ¥{{ sumUsage('cost_yuan').toFixed(4) }}
          </p>
        </el-card>
      </el-col>

      <el-col :span="14">
        <el-card shadow="never" class="block">
          <template #header>对话记录（含客户内心独白）</template>
          <div class="chat">
            <div v-for="m in data.messages" :key="m.seq" :class="['row', m.role]">
              <div class="meta">
                <el-tag size="small" :type="m.role === 'user' ? 'primary' : m.role === 'hint' ? 'warning' : 'danger'" effect="plain">
                  {{ ROLE[m.role] }}
                </el-tag>
                <span v-if="m.trust_after != null" class="muted">
                  信任 {{ m.trust_after }}（{{ (m.trust_delta ?? 0) >= 0 ? '+' : '' }}{{ m.trust_delta }}）
                </span>
              </div>
              <div class="bubble">{{ m.content }}</div>
              <div v-if="m.inner_thought" class="thought">内心：{{ m.inner_thought }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.block {
  margin-top: 16px;
  margin-bottom: 16px;
}
.summary {
  margin: 0 0 8px;
  line-height: 1.6;
}
.sub {
  margin: 14px 0 6px;
  font-weight: 600;
}
.tag {
  margin: 0 6px 6px 0;
}
.note,
.muted {
  color: #86909c;
  font-size: 12px;
}
.chat {
  max-height: 720px;
  overflow-y: auto;
}
.row {
  margin-bottom: 14px;
}
.row.user {
  text-align: right;
}
.meta {
  margin-bottom: 4px;
}
.bubble {
  display: inline-block;
  max-width: 80%;
  padding: 8px 12px;
  border-radius: 8px;
  background: #f2f3f5;
  text-align: left;
  line-height: 1.6;
}
.row.user .bubble {
  background: #e8f1ff;
}
.row.hint .bubble {
  background: #fff7e8;
}
.thought {
  margin-top: 4px;
  color: #86909c;
  font-size: 12px;
  font-style: italic;
}
</style>
