<script setup lang="ts">
import { api } from '@/api'
import type { KnowledgeEventCard, KnowledgeEventDetail, KnowledgeReviewData, KnowledgeReviewIn } from '@/types'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, nextTick, onMounted, ref, toRaw } from 'vue'

const states: Record<string, string> = { pending: '待审核', approved: '已通过', rejected: '已驳回' }
const loading = ref(false)
const saving = ref(false)
const opened = ref(false)
const status = ref('')
const page = ref(1)
const total = ref(0)
const rows = ref<KnowledgeEventCard[]>([])
const detail = ref<KnowledgeEventDetail | null>(null)
const form = ref<KnowledgeReviewData | null>(null)
const note = ref('')
const actions = ref('')
const limits = ref('')
const full = ref(false)
const dirty = ref(false)
const segments = computed(() => detail.value?.segments.filter(s => full.value || (s.seq >= detail.value!.segment_start && s.seq <= detail.value!.segment_end)) ?? [])

async function load() {
  loading.value = true
  try {
    const r = await api.admin.knowledgeEvents({ status: status.value, page: page.value, size: 20 })
    rows.value = r.items; total.value = r.total
  } catch (e) { ElMessage.error((e as Error).message) }
  finally { loading.value = false }
}
function apply(d: KnowledgeEventDetail) {
  detail.value = d; form.value = structuredClone(d.data)
  actions.value = d.data.labels.agent_actions.join('、')
  limits.value = d.data.applicability_limits.join('\n'); note.value = ''; dirty.value = false
}
async function open(row: KnowledgeEventCard) {
  loading.value = true
  try { apply(await api.admin.knowledgeEvent(row.id)); full.value = false; opened.value = true }
  catch (e) { ElMessage.error((e as Error).message) }
  finally { loading.value = false }
}
async function close(done: () => void) {
  if (saving.value) return
  if (dirty.value) {
    try { await ElMessageBox.confirm('有未保存的修改，确定关闭吗？', '关闭核对') }
    catch { return }
  }
  done()
}
async function locate(seq: number) {
  if (!detail.value) return
  full.value = true; await nextTick()
  document.getElementById(`segment-${seq}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
async function submit(action: KnowledgeReviewIn['action']) {
  if (!detail.value || !form.value || saving.value) return
  if (!form.value.title.trim() || !form.value.summary.trim()) return ElMessage.warning('请填写标题和总结')
  if (action === 'reject' && !note.value.trim()) return ElMessage.warning('请填写驳回原因')
  if (action === 'approve') {
    try { await ElMessageBox.confirm('通过仅表示事件内容已核对，不代表隐私、角色或政策已核验，也不会启用检索。', '确认通过') }
    catch { return }
  }
  saving.value = true
  try {
    const data = structuredClone(toRaw(form.value))
    data.labels.agent_actions = actions.value.split(/[、,，\n]/).map(s => s.trim()).filter(Boolean)
    data.applicability_limits = limits.value.split('\n').map(s => s.trim()).filter(Boolean)
    apply(await api.admin.reviewKnowledgeEvent(detail.value.id, { action, expected_revision: detail.value.revision, data, note: note.value }))
    ElMessage.success(action === 'save' ? '已保存为待审核' : action === 'approve' ? '已通过，尚未启用检索' : '已驳回')
    await load()
  } catch (e) { ElMessage.error((e as Error).message) }
  finally { saving.value = false }
}
onMounted(load)
</script>

<template>
  <el-card shadow="never">
    <h2>知识案例</h2>
    <p class="muted">对照完整转写核对提取结果。原始提取保留，人工修改和每次审核单独留档。</p>
    <el-select v-model="status" placeholder="全部状态" clearable style="width: 160px; margin-bottom: 16px" @change="page = 1; load()">
      <el-option v-for="(label, value) in states" :key="value" :label="label" :value="value" />
    </el-select>
    <el-table v-loading="loading" :data="rows" stripe>
      <el-table-column prop="event_key" label="事件" width="90" />
      <el-table-column prop="title" label="标题" min-width="240" />
      <el-table-column prop="source_key" label="来源标识" min-width="210" />
      <el-table-column label="原文范围" width="120"><template #default="{ row }">{{ row.segment_start }}–{{ row.segment_end }}</template></el-table-column>
      <el-table-column label="审核" width="110"><template #default="{ row }"><el-tag>{{ states[row.status] }}</el-tag></template></el-table-column>
      <el-table-column label="操作" width="110"><template #default="{ row }"><el-button type="primary" link @click="open(row as KnowledgeEventCard)">查看并核对</el-button></template></el-table-column>
      <template #empty><el-empty description="暂无知识事件，请先导入已有转写与提取结果" /></template>
    </el-table>
    <el-pagination v-model:current-page="page" :total="total" :page-size="20" layout="prev, pager, next, total" @current-change="load" />
  </el-card>

  <el-drawer v-model="opened" title="知识事件核对" size="94%" :before-close="close" destroy-on-close>
    <template v-if="detail && form">
      <el-alert type="warning" :closable="false" title="仅完成基础脱敏，角色、政策和时间单位仍需核验。通过审核不会自动启用检索。" />
      <p class="muted">{{ detail.event_key }} · 原文 {{ detail.segment_start }}–{{ detail.segment_end }} · {{ states[detail.status] }} · 修订 {{ detail.revision }}</p>
      <div class="panes">
        <section>
          <div class="section-heading"><h3>转写原文</h3><el-switch v-model="full" active-text="完整转写" inactive-text="事件上下文" /></div>
          <p class="muted">声道角色为当前推定；时间仅显示源值，不换算为秒。</p>
          <div class="transcript">
            <article v-for="s in segments" :id="`segment-${s.seq}`" :key="s.seq" :class="{ evidence: detail.evidence_seqs.includes(s.seq), context: s.seq >= detail.segment_start && s.seq <= detail.segment_end }">
              <small>#{{ s.seq }} · 声道 {{ s.channel }}（{{ detail.speaker_mapping[String(s.channel)] === 'agent' ? '坐席推定' : detail.speaker_mapping[String(s.channel)] === 'customer' ? '客户推定' : '未确认' }}） · {{ s.start_raw }} → {{ s.end_raw }}</small>
              <p>{{ s.text }}</p><el-tag v-if="detail.evidence_seqs.includes(s.seq)" size="small">关键证据</el-tag>
            </article>
          </div>
        </section>
        <section>
          <h3>提取结果与人工修订</h3>
          <div class="evidence-links"><span>定位证据：</span><el-button v-for="seq in detail.evidence_seqs" :key="seq" size="small" @click="locate(seq)">#{{ seq }}</el-button></div>
          <el-form label-position="top" @input="dirty = true" @change="dirty = true">
            <el-form-item label="标题"><el-input v-model="form.title" maxlength="256" /></el-form-item>
            <div class="fields">
              <el-form-item label="客户问题"><el-input v-model="form.labels.customer_problem" /></el-form-item>
              <el-form-item label="沟通阶段"><el-input v-model="form.labels.stage" /></el-form-item>
            </div>
            <el-form-item label="坐席动作（用顿号分隔）"><el-input v-model="actions" /></el-form-item>
            <el-form-item label="可观察结果"><el-input v-model="form.labels.observed_result" /></el-form-item>
            <el-form-item label="事件总结"><el-input v-model="form.summary" type="textarea" :rows="4" maxlength="10000" /></el-form-item>
            <el-form-item label="适用边界与未决问题（每行一条）"><el-input v-model="limits" type="textarea" :rows="3" /></el-form-item>
            <el-form-item label="审核说明（驳回必填）"><el-input v-model="note" type="textarea" :rows="2" maxlength="2000" /></el-form-item>
          </el-form>
          <el-collapse>
            <el-collapse-item title="原始提取结果（只读）" name="original"><pre>{{ JSON.stringify(detail.original, null, 2) }}</pre></el-collapse-item>
            <el-collapse-item :title="`审核历史（${detail.history.length}）`" name="history">
              <el-empty v-if="!detail.history.length" description="暂无审核记录" :image-size="40" />
              <div v-for="h in [...detail.history].reverse()" :key="h.revision" class="history"><b>修订 {{ h.revision }} · {{ { save: '保存待审核', approve: '通过', reject: '驳回' }[h.action as 'save' | 'approve' | 'reject'] }}</b><p>{{ h.at }} · 操作人 #{{ h.user_id }}</p><p>{{ h.note || '无备注' }}</p></div>
            </el-collapse-item>
          </el-collapse>
        </section>
      </div>
    </template>
    <template #footer><el-button :disabled="saving" @click="submit('save')">保存待审核</el-button><el-button :disabled="saving" type="danger" plain @click="submit('reject')">驳回</el-button><el-button :loading="saving" type="primary" @click="submit('approve')">通过审核</el-button></template>
  </el-drawer>
</template>

<style scoped>
h2,h3 { margin: 0 0 12px; }
.muted,small { color: #64748b; font-size: 13px; }
.panes { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
.panes section { min-width: 0; }
.section-heading,.fields { display: flex; justify-content: space-between; gap: 12px; }
.fields > * { flex: 1; min-width: 0; }
.transcript { max-height: 66vh; overflow: auto; border: 1px solid #e2e8f0; border-radius: 8px; }
article { padding: 12px; border-bottom: 1px solid #e2e8f0; }
article p { margin: 6px 0; line-height: 1.7; white-space: pre-wrap; }
article.context { background: #f8fafc; }
article.evidence { background: #eff6ff; border-left: 3px solid #3b82f6; }
.evidence-links { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 16px; }
.evidence-links .el-button + .el-button { margin-left: 0; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; }
.history { border-bottom: 1px solid #e2e8f0; padding: 10px 0; }
.el-pagination { margin-top: 16px; }
@media (max-width: 900px) { .panes { grid-template-columns: 1fr; } .transcript { max-height: 40vh; } }
</style>
