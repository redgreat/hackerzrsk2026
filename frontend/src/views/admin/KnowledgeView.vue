<script setup lang="ts">
import { api } from '@/api'
import type { KnowledgeItem } from '@/types'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

const loading = ref(false)
const saving = ref(false)
const rows = ref<KnowledgeItem[]>([])
const createVisible = ref(false)
const importVisible = ref(false)
const form = reactive({ title: '', content: '', tags: '', scenario_ids: '' })
const importForm = reactive({ name: '', text: '' })

const splitList = (s: string) => s.split(/[,，、\s]+/).map((x) => x.trim()).filter(Boolean)

async function load() {
  loading.value = true
  try {
    rows.value = await api.admin.knowledge()
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

async function submitCreate() {
  if (!form.title.trim() || !form.content.trim()) return ElMessage.warning('标题和内容不能为空')
  saving.value = true
  try {
    await api.admin.createKnowledge({
      title: form.title.trim(),
      content: form.content.trim(),
      tags: splitList(form.tags),
      scenario_ids: splitList(form.scenario_ids),
    })
    ElMessage.success('已新增')
    createVisible.value = false
    Object.assign(form, { title: '', content: '', tags: '', scenario_ids: '' })
    await load()
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    saving.value = false
  }
}

async function submitImport() {
  if (!importForm.name.trim() || !importForm.text.trim()) return ElMessage.warning('名称和内容不能为空')
  saving.value = true
  try {
    const r = await api.admin.importKnowledge(importForm.name.trim(), importForm.text)
    ElMessage.success(`已导入 ${r.imported} 个片段`)
    importVisible.value = false
    Object.assign(importForm, { name: '', text: '' })
    await load()
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    saving.value = false
  }
}

async function remove(row: KnowledgeItem) {
  try {
    await ElMessageBox.confirm(`确定删除「${row.title}」？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.admin.deleteKnowledge(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

async function rebuild() {
  try {
    await ElMessageBox.confirm(
      '将重新加载服务器 knowledge/ 目录中的 Markdown，并为缺失向量的片段补算 embedding。手动新增的片段不受影响。继续？',
      '重建知识库',
      { type: 'info' },
    )
  } catch {
    return
  }
  loading.value = true
  try {
    const r = await api.admin.rebuildKnowledge()
    ElMessage.success(`已加载 ${r.loaded_from_dir} 个目录片段，补算向量 ${r.embeddings_filled} 个`)
    await load()
  } catch (e) {
    ElMessage.error((e as Error).message)
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <el-card shadow="never">
    <div class="toolbar">
      <el-button type="primary" @click="createVisible = true">新增片段</el-button>
      <el-button @click="importVisible = true">粘贴导入 Markdown</el-button>
      <el-button @click="rebuild">重建（加载服务器目录）</el-button>
      <span class="muted">共 {{ rows.length }} 个片段</span>
    </div>

    <el-table v-loading="loading" :data="rows" stripe>
      <el-table-column prop="title" label="标题" min-width="220" />
      <el-table-column prop="source" label="来源" min-width="180" show-overflow-tooltip />
      <el-table-column label="标签" min-width="160">
        <template #default="{ row }">
          <el-tag v-for="t in row.tags" :key="t" size="small" class="tag" effect="plain">{{ t }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="适用场景" width="130">
        <template #default="{ row }">{{ row.scenario_ids.length ? row.scenario_ids.join('、') : '通用' }}</template>
      </el-table-column>
      <el-table-column label="检索方式" width="100">
        <template #default="{ row }">{{ row.has_embedding ? '向量' : '关键词' }}</template>
      </el-table-column>
      <el-table-column prop="preview" label="内容摘要" min-width="260" show-overflow-tooltip />
      <el-table-column label="操作" width="90" fixed="right">
        <template #default="{ row }">
          <el-button type="danger" link @click="remove(row as KnowledgeItem)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="createVisible" title="新增知识片段" width="560px">
      <el-form label-width="90px">
        <el-form-item label="标题"><el-input v-model="form.title" maxlength="256" /></el-form-item>
        <el-form-item label="内容"><el-input v-model="form.content" type="textarea" :rows="8" placeholder="请先脱敏，不要填写真实客户信息" /></el-form-item>
        <el-form-item label="标签"><el-input v-model="form.tags" placeholder="逗号分隔，如 异议处理, 价值塑造" /></el-form-item>
        <el-form-item label="适用场景"><el-input v-model="form.scenario_ids" placeholder="场景 ID，如 S01, S02；留空为通用" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitCreate">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="importVisible" title="粘贴导入 Markdown" width="640px">
      <el-form label-width="90px">
        <el-form-item label="名称"><el-input v-model="importForm.name" placeholder="如 sales_objections.md（同名再次导入会替换）" /></el-form-item>
        <el-form-item label="内容">
          <el-input
            v-model="importForm.text"
            type="textarea"
            :rows="14"
            placeholder="可用 front matter：---\ntitle: 标题\ntags: [异议处理]\nscenarios: [S01]\n---\n然后用 ## 二级标题分段"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitImport">导入</el-button>
      </template>
    </el-dialog>
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
.tag {
  margin-right: 4px;
}
</style>
