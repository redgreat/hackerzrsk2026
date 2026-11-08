<script setup lang="ts">
import { api } from '@/api'
import type { KnowledgeItem } from '@/types'
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'

const loading = ref(false)
const rows = ref<KnowledgeItem[]>([])

onMounted(async () => {
  loading.value = true
  try {
    rows.value = await api.admin.knowledge()
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <el-card shadow="never">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="tip"
      title="知识库内容来自 knowledge/*.md（必须已脱敏）。修改后在后端执行 python -m app.cli ingest-knowledge 入库。"
    />
    <el-table v-loading="loading" :data="rows" stripe>
      <el-table-column prop="title" label="标题" min-width="220" />
      <el-table-column prop="source" label="来源文件" min-width="200" />
      <el-table-column label="标签" min-width="160">
        <template #default="{ row }">
          <el-tag v-for="t in row.tags" :key="t" size="small" class="tag" effect="plain">{{ t }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="适用场景" width="130">
        <template #default="{ row }">{{ row.scenario_ids.length ? row.scenario_ids.join('、') : '通用' }}</template>
      </el-table-column>
      <el-table-column label="检索方式" width="110">
        <template #default="{ row }">{{ row.has_embedding ? '向量' : '关键词' }}</template>
      </el-table-column>
      <el-table-column prop="preview" label="内容摘要" min-width="300" show-overflow-tooltip />
    </el-table>
  </el-card>
</template>

<style scoped>
.tip {
  margin-bottom: 16px;
}
.tag {
  margin-right: 4px;
}
</style>
