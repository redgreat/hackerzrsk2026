<script setup lang="ts">
import { api } from '@/api'
import type { OpsSetting } from '@/types'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

const loading = ref(false)
const items = ref<OpsSetting[]>([])
const drafts = ref<Record<string, boolean | number | string>>({})

const groups = computed(() => {
  const map = new Map<string, OpsSetting[]>()
  for (const i of items.value) map.set(i.group, [...(map.get(i.group) ?? []), i])
  return [...map.entries()]
})

async function load() {
  loading.value = true
  try {
    items.value = await api.admin.settings()
    drafts.value = Object.fromEntries(items.value.map((i) => [i.key, i.value]))
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

async function save(item: OpsSetting) {
  try {
    await api.admin.saveSetting(item.key, drafts.value[item.key])
    ElMessage.success(`已保存：${item.label}`)
    await load()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

async function reset(item: OpsSetting) {
  try {
    await ElMessageBox.confirm(`将「${item.label}」恢复为 config.yml 的默认值？`, '恢复默认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.admin.resetSetting(item.key)
    ElMessage.success('已恢复默认')
    await load()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

const dirty = (item: OpsSetting) => drafts.value[item.key] !== item.value

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="tip"
      title="这里只放非敏感的运维项，修改后即时生效，并记录操作人。密钥、数据库连接、JWT、管理员工号仍只在服务器的 config.yml 中维护。"
    />

    <el-card v-for="[group, list] in groups" :key="group" shadow="never" class="block">
      <template #header>{{ group }}</template>
      <el-form label-width="200px" label-position="left">
        <el-form-item v-for="item in list" :key="item.key">
          <template #label>
            <span>{{ item.label }}</span>
            <el-tooltip v-if="item.hint" :content="item.hint" placement="top">
              <el-icon class="hint"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <div class="row">
            <el-switch v-if="item.kind === 'bool'" v-model="drafts[item.key]" />
            <el-select v-else-if="item.kind === 'choice'" v-model="drafts[item.key]" style="width: 220px">
              <el-option v-for="c in item.choices" :key="c" :label="c" :value="c" />
            </el-select>
            <el-input-number
              v-else-if="item.kind === 'int' || item.kind === 'float'"
              v-model="drafts[item.key] as number"
              :min="item.min ?? undefined"
              :max="item.max ?? undefined"
              :precision="item.kind === 'float' ? 2 : 0"
              controls-position="right"
            />
            <el-input v-else v-model="drafts[item.key] as string" style="width: 260px" />

            <el-button type="primary" size="small" :disabled="!dirty(item)" @click="save(item)">保存</el-button>
            <el-button v-if="item.overridden" size="small" @click="reset(item)">恢复默认</el-button>
            <span class="meta">
              <template v-if="item.overridden">已后台修改 · {{ item.updated_by }} · {{ item.updated_at?.slice(0, 16).replace('T', ' ') }}</template>
              <template v-else>默认（config.yml）</template>
            </span>
          </div>
        </el-form-item>
      </el-form>
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
.row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.hint {
  margin-left: 4px;
  color: #86909c;
  cursor: help;
}
.meta {
  color: #86909c;
  font-size: 12px;
}
</style>
