<script setup lang="ts">
import { api } from '@/api'
import type { KnowledgeBundle, KnowledgeForm, KnowledgeItem } from '@/types'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

const rows = ref<KnowledgeItem[]>([])
const busy = ref(false)
const open = ref(false)
const filter = ref('')
const editing = ref<string>()
const form = ref<KnowledgeForm>(blank())
const tags = ref('')
const scenarioIds = ref('')
const fileInput = ref<HTMLInputElement>()
const categories = computed(() => [...new Set(rows.value.map((row) => row.category))])
const filtered = computed(() => rows.value.filter((row) => !filter.value || row.category === filter.value))

function blank(): KnowledgeForm {
  return { category: '', title: '', content: '', enabled: true, tags: [], scenario_ids: [] }
}

function edit(row?: KnowledgeItem) {
  editing.value = row?.id
  form.value = row ? { ...row } : blank()
  tags.value = row?.tags.join('、') ?? ''
  scenarioIds.value = row?.scenario_ids.join('、') ?? ''
  open.value = true
}

async function load() {
  rows.value = await api.admin.knowledge()
  if (!categories.value.includes(filter.value)) filter.value = ''
}

async function perform(action: () => Promise<void>) {
  busy.value = true
  try {
    await action()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    busy.value = false
  }
}

function save() {
  return perform(async () => {
    const split = (value: string) => value.split(/[,，、\n]/).map((item) => item.trim()).filter(Boolean)
    const body = { ...form.value, tags: split(tags.value), scenario_ids: split(scenarioIds.value) }
    if (editing.value) await api.admin.editKnowledge(editing.value, body)
    else await api.admin.addKnowledge(body)
    open.value = false
    await load()
    ElMessage.success('话术已保存')
  })
}

function download() {
  return perform(async () => {
    const bundle = await api.admin.exportKnowledge()
    const url = URL.createObjectURL(new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' }))
    const link = document.createElement('a')
    link.href = url
    link.download = '话术知识库.json'
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  })
}

function importFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  return perform(async () => {
    let bundle: KnowledgeBundle
    try {
      bundle = JSON.parse(await file.text())
      if (bundle?.version !== 1 || !Array.isArray(bundle.scripts)) throw new Error()
    } catch {
      throw new Error('请选择从话术知识库导出的 JSON 文件')
    }
    try {
      await ElMessageBox.confirm(`将导入 ${bundle.scripts.length} 条话术，编号相同的记录会更新。`, '导入话术')
    } catch {
      return
    }
    const result = await api.admin.importKnowledge(bundle)
    await load()
    ElMessage.success(`已导入 ${result.imported} 条话术`)
  })
}

onMounted(() => perform(load))
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <div class="toolbar">
        <el-button type="primary" :disabled="busy" @click="edit()">新增话术</el-button>
        <el-button :disabled="busy" @click="fileInput?.click()">导入 JSON</el-button>
        <el-button :disabled="busy" @click="download">导出 JSON</el-button>
        <input ref="fileInput" type="file" accept=".json,application/json" hidden @change="importFile" />
        <el-select v-model="filter" clearable placeholder="全部分类" style="width: 180px" aria-label="筛选话术分类">
          <el-option v-for="category in categories" :key="category" :value="category" />
        </el-select>
      </div>
    </template>
    <el-table v-loading="busy" :data="filtered" stripe empty-text="暂无话术">
      <el-table-column prop="category" label="分类" min-width="160" />
      <el-table-column prop="title" label="标题" min-width="240" />
      <el-table-column prop="content" label="话术" min-width="260" show-overflow-tooltip />
      <el-table-column label="状态" width="100">
        <template #default="{ row }"><el-tag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '已启用' : '已停用' }}</el-tag></template>
      </el-table-column>
      <el-table-column label="操作" width="90">
        <template #default="{ row }"><el-button link type="primary" @click="edit(row as KnowledgeItem)">编辑</el-button></template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-dialog v-model="open" :title="editing ? '编辑话术' : '新增话术'" width="min(640px, 92vw)">
    <el-form label-position="top" @submit.prevent>
      <el-form-item label="分类"><el-input v-model="form.category" maxlength="64" /></el-form-item>
      <el-form-item label="标题"><el-input v-model="form.title" maxlength="256" /></el-form-item>
      <el-form-item label="正文（填写脱敏后的话术）"><el-input v-model="form.content" type="textarea" :rows="5" /></el-form-item>
      <el-form-item label="标签"><el-input v-model="tags" placeholder="多个标签用逗号分隔" /></el-form-item>
      <el-form-item label="适用练习"><el-input v-model="scenarioIds" placeholder="填写练习编号，留空表示通用" /></el-form-item>
      <el-form-item label="允许 AI 教练检索">
        <el-radio-group v-model="form.enabled"><el-radio :value="true">启用</el-radio><el-radio :value="false">停用</el-radio></el-radio-group>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button :disabled="busy" @click="open = false">取消</el-button>
      <el-button type="primary" :loading="busy" :disabled="!form.category.trim() || !form.title.trim() || !form.content.trim()" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
</style>
