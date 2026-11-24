<script setup lang="ts">
import { api } from '@/api'
import type { RubricForm, RubricVersion } from '@/types'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

const history = ref<RubricVersion[]>([])
const form = ref<RubricForm>()
const redLines = ref('')
const selected = ref(0)
const busy = ref(false)
const latest = computed(() => history.value[0]?.version ?? 0)
const totalWeight = computed(() => form.value?.dimensions.reduce((sum, d) => sum + (d.weight || 0), 0) ?? 0)

function loadVersion(version: number) {
  const entry = history.value.find((item) => item.version === version)
  if (!entry) return
  form.value = JSON.parse(JSON.stringify(entry.rubric))
  redLines.value = entry.rubric.red_lines.join('\n')
  selected.value = version
}

async function load() {
  history.value = (await api.admin.rubric()).versions
  loadVersion(latest.value)
}

async function publish() {
  if (!form.value || busy.value) return
  try {
    await ElMessageBox.confirm('发布后，新开的练习和答卷会使用这份评分标准。', '发布评分标准')
  } catch {
    return
  }
  busy.value = true
  try {
    const result = await api.admin.publishRubric({
      ...form.value,
      red_lines: redLines.value.split('\n').map((line) => line.trim()).filter(Boolean),
      base_version: latest.value,
    })
    await load()
    ElMessage.success(`已发布第 ${result.version} 版`)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  try {
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
})
</script>

<template>
  <el-card v-if="form" shadow="never">
    <template #header>
      <div class="toolbar">
        <strong>当前生效 · 第 {{ latest }} 版</strong>
        <el-select :model-value="selected" aria-label="读取历史版本" style="width: 220px"
          :disabled="busy" @change="loadVersion">
          <el-option v-for="entry in history" :key="entry.version" :value="entry.version"
            :label="entry.version === latest ? `第 ${entry.version} 版（当前）` : `第 ${entry.version} 版（历史）`" />
        </el-select>
        <el-button type="primary" :loading="busy" @click="publish">发布新版本</el-button>
      </div>
    </template>
    <el-form label-position="top" :disabled="busy" @submit.prevent>
      <el-form-item label="评分表名称">
        <el-input v-model="form.name" maxlength="100" />
      </el-form-item>
      <div class="toolbar">
        <h3>评分维度 · 权重合计 {{ totalWeight }}</h3>
        <el-button :disabled="form.dimensions.length >= 20"
          @click="form.dimensions.push({ name: '', weight: 10, good: '', bad: '' })">添加维度</el-button>
      </div>
      <div v-for="(dimension, index) in form.dimensions" :key="index" class="dimension">
        <el-form-item label="维度名称"><el-input v-model="dimension.name" /></el-form-item>
        <el-form-item label="权重"><el-input-number v-model="dimension.weight" :min="0.01" /></el-form-item>
        <el-form-item label="5 分表现"><el-input v-model="dimension.good" type="textarea" /></el-form-item>
        <el-form-item label="1 分表现"><el-input v-model="dimension.bad" type="textarea" /></el-form-item>
        <el-form-item label="操作">
          <el-button type="danger" link :disabled="form.dimensions.length === 1"
            @click="form.dimensions.splice(index, 1)">移除</el-button>
        </el-form-item>
      </div>
      <div class="toolbar">
        <el-form-item label="每次求助扣分">
          <el-input-number v-model="form.hint_penalty" :min="0" :max="100" />
        </el-form-item>
        <el-form-item label="累计求助扣分上限">
          <el-input-number v-model="form.hint_penalty_max" :min="0" :max="100" />
        </el-form-item>
        <el-form-item label="触发红线时的总分上限">
          <el-input-number v-model="form.red_line_cap" :min="0" :max="100" :precision="0" />
        </el-form-item>
      </div>
      <el-form-item label="合规红线（每行一条）">
        <el-input v-model="redLines" type="textarea" :rows="6" />
      </el-form-item>
    </el-form>
  </el-card>
</template>

<style scoped>
.toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.dimension {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
  padding: 12px 0 0;
  border-top: 1px solid var(--el-border-color-light);
}
</style>
