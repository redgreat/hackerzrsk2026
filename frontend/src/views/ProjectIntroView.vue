<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

const chapters = [
  {
    name: '项目介绍',
    title: 'AI 客户话术陪练',
    description: '面向规模化服务团队的沟通培训工具。让服务经验可以学、可以练，也可以通过考核检验。',
    points: ['客服与一线服务', '销售与客户沟通', '售后与问题处理'],
    visual: '适用岗位',
    icon: 'friends-o',
  },
  {
    name: '项目背景',
    title: '话术听过了，\n开口还是难。',
    description: '一线服务离不开客户沟通。新人需要练习如何问清问题、安抚情绪，并在合规范围内推进下一步。',
    points: ['缺少能反复对练的真实感对手', '成熟话术难变成互动能力', '流程更新快，传统带教周期长'],
    visual: '新员工带教',
    icon: 'records-o',
  },
  {
    name: '项目目标',
    title: '人人随时可练，\n练完有依据。',
    description: '用 AI 分担老员工陪练，让新人随时反复练。把脱敏后的成熟话术用于求助和评分，从听过、敢开口，到会开口。',
    points: ['降本 · 减少重复陪练', '增效 · 从听过到敢开口', '提质 · 统一评分与合规标准'],
    visual: '从学习到实战',
    icon: 'aim',
  },
  {
    name: '录音学习',
    title: '把优秀沟通，\n变成能练的场景。',
    description: '复用已有 AI 转写。管理员生成并审核练习，随录音一起发布。员工可收听原录音、搜索转写，再进入对应场景。',
    points: ['优秀录音与已有转写', 'AI 提取训练场景', '人工审核后发布'],
    visual: '一条录音，多种练法',
    icon: 'music-o',
    link: { to: '/recordings', label: '打开录音学习' },
  },
  {
    name: 'AI 实战',
    title: '客户会追问，\n教练能点评。',
    description: 'AI 扮演有顾虑的客户，按学员的表达作出回应。遇到卡点可求助，练完回看分项评分和改进建议。',
    points: ['选场景 · 先看背景与目标', '多轮对练 · 必要时向教练求助', '练后报告 · 对照原话改进'],
    visual: '练习片段 · 示例',
    icon: 'chat-o',
    link: { to: '/', label: '选择练习场景' },
  },
  {
    name: '练后复盘',
    title: '知道哪里做得好，\n下次改哪一句。',
    description: '评分报告把对话和评分标准放在一起。学员可从练习历史回看表现，管理员可查看练习情况和模型用量。',
    points: ['核对分项得分和合规红线', '回看逐轮点评与改进建议', '在练习历史里追踪表现'],
    visual: 'AI 教练报告',
    icon: 'chart-trending-o',
    link: { to: '/history', label: '查看练习历史' },
  },
  {
    name: '考试与管理',
    title: '让练习成果，\n经得起考核。',
    description: '正式考试从已审核的合规题和录音练习中随机组卷。管理后台可维护话术和评分版本，查看练习记录与考试成绩。',
    points: ['AI 出题 · 审核后入库', '随机组卷 · 限时完成', '后台复盘 · 分项评分与成绩'],
    visual: '催收新人上岗考试',
    icon: 'records-o',
    link: { to: '/exams', label: '打开考试入口' },
  },
] as const

const index = ref(0)
const playing = ref(false)
const fullscreen = ref(false)
const stage = ref<HTMLElement>()
const chapter = computed(() => chapters[index.value]!)
const link = computed(() => 'link' in chapter.value ? chapter.value.link : undefined)
let timer: ReturnType<typeof setTimeout> | undefined

function select(next: number) {
  index.value = Math.min(Math.max(next, 0), chapters.length - 1)
}

function togglePlay() {
  if (!playing.value && index.value === chapters.length - 1) select(0)
  playing.value = !playing.value
}

watch([index, playing], () => {
  clearTimeout(timer)
  if (!playing.value) return
  timer = setTimeout(() => {
    if (index.value === chapters.length - 1) playing.value = false
    else select(index.value + 1)
  }, 9500)
})

async function toggleFullscreen() {
  try {
    if (document.fullscreenElement) await document.exitFullscreen()
    else await stage.value?.requestFullscreen()
  } catch {
    // 部分移动端浏览器不支持元素全屏，仍可正常浏览。
  }
}

function onFullscreen() {
  fullscreen.value = document.fullscreenElement === stage.value
}

function onKey(event: KeyboardEvent) {
  if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || event.defaultPrevented) return
  if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
    event.preventDefault()
    select(index.value + (event.key === 'ArrowRight' ? 1 : -1))
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKey)
  document.addEventListener('fullscreenchange', onFullscreen)
})
onUnmounted(() => {
  clearTimeout(timer)
  window.removeEventListener('keydown', onKey)
  document.removeEventListener('fullscreenchange', onFullscreen)
})
</script>

<template>
  <main ref="stage" class="intro">
    <div class="shell">
      <header class="topbar">
        <RouterLink to="/" class="brand"><span class="brand-icon"><van-icon name="chat-o" /></span> AI 客户话术陪练</RouterLink>
        <button v-if="stage?.requestFullscreen" class="control fullscreen" type="button" @click="toggleFullscreen">
          {{ fullscreen ? '退出全屏' : '全屏展示' }}
        </button>
      </header>

      <div class="chapter-frame">
        <Transition name="chapter">
          <section :key="index" class="stage" :aria-labelledby="`chapter-title-${index}`">
            <div class="copy">
              <p class="chapter-name">{{ chapter.name }}</p>
              <h1 :id="`chapter-title-${index}`">{{ chapter.title }}</h1>
              <p class="description">{{ chapter.description }}</p>
              <RouterLink v-if="link" :to="link.to" class="feature-link">{{ link.label }} <van-icon name="arrow" /></RouterLink>
            </div>
            <div class="visual">
              <div class="visual-head"><van-icon :name="chapter.icon" /> {{ chapter.visual }}</div>
              <div v-if="chapter.name === '录音学习'" class="wave" aria-hidden="true">
                <i v-for="(height, i) in [18, 35, 23, 48, 69, 39, 81, 52, 27, 58, 72, 31, 45, 23, 36, 18]" :key="i" :style="{ '--h': height + 'px', '--delay': i * 45 + 'ms' }" />
              </div>
              <div v-if="chapter.name === 'AI 实战'" class="dialogue">
                <p>这笔转账银行显示成功了，怎么还没到账？</p>
                <p>我先帮您核对交易状态。核实前，您先不用重复付款。</p>
              </div>
              <dl v-if="chapter.name === '考试与管理'" class="exam-facts">
                <div><dt>合规题</dt><dd>12 道</dd></div>
                <div><dt>情景对练</dt><dd>2 场</dd></div>
                <div><dt>开考时限</dt><dd>60 分钟</dd></div>
              </dl>
              <ol class="points">
                <li v-for="(point, i) in chapter.points" :key="point" :style="{ '--delay': (i + 1) * 95 + 'ms' }">
                  <span class="point-icon"><van-icon :name="chapter.name === '项目背景' ? 'minus' : 'success'" /></span>{{ point }}
                </li>
              </ol>
            </div>
          </section>
        </Transition>
      </div>

      <footer class="navigation">
        <nav aria-label="项目介绍章节">
          <button v-for="(item, i) in chapters" :key="item.name" type="button" :aria-current="i === index ? 'step' : undefined" @click="select(i)">
            {{ item.name }}
          </button>
        </nav>
        <div class="actions">
          <button class="control" type="button" aria-label="上一章" :disabled="index === 0" @click="select(index - 1)"><van-icon name="arrow-left" /></button>
          <button class="control play" type="button" :aria-pressed="playing" @click="togglePlay">{{ playing ? '暂停播放' : '自动播放' }}</button>
          <button class="control" type="button" aria-label="下一章" :disabled="index === chapters.length - 1" @click="select(index + 1)"><van-icon name="arrow" /></button>
        </div>
      </footer>
    </div>
  </main>
</template>

<style scoped>
.intro {
  --ink: #ecf8f3;
  --muted: #a8c0b9;
  --accent: #aff3cc;
  min-height: 100dvh;
  overflow: auto;
  color: var(--ink);
  background: radial-gradient(ellipse at 84% 22%, #1b4b3e, transparent 49%), #0c201d;
}
.shell { max-width: 1320px; margin: auto; padding: 0 clamp(20px, 6vw, 90px); }
.topbar, .navigation { display: flex; align-items: center; justify-content: space-between; gap: 18px; }
.topbar { min-height: 76px; border-bottom: 1px solid #bed8cd30; }
.brand, .feature-link { display: inline-flex; align-items: center; gap: 10px; color: var(--ink); text-decoration: none; font-weight: 650; }
.brand-icon, .point-icon { display: grid; place-items: center; background: #b4f2ce1e; color: var(--accent); border-radius: 10px; }
.brand-icon { width: 34px; height: 34px; font-size: 20px; }
.chapter-frame { display: grid; }
.stage { grid-area: 1 / 1; display: grid; grid-template-columns: 1.1fr 1fr; align-items: center; gap: clamp(20px, 6vw, 90px); min-height: min(600px, 68vh); padding-block: 32px; box-sizing: border-box; }
.chapter-name { margin: 0 0 16px; color: var(--accent); font-weight: 650; letter-spacing: .1em; }
h1 { margin: 0; font-size: clamp(34px, 5.3vw, 78px); letter-spacing: -.045em; line-height: 1.13; white-space: pre-line; }
.description { max-width: 32em; color: var(--muted); font-size: clamp(15px, 1.5vw, 20px); line-height: 1.8; margin: 22px 0 0; }
.feature-link { margin-top: 20px; color: var(--accent); }
.visual { min-width: 0; padding: clamp(16px, 3vw, 36px); border: 1px solid #b8ead142; border-radius: 24px; background: #16342ed9; box-shadow: 0 24px 65px #06171248; }
.visual-head { display: flex; align-items: center; gap: 10px; color: var(--accent); font-size: 17px; font-weight: 650; }
.points { margin: 18px 0 0; padding: 0; list-style: none; display: grid; gap: 9px; }
.points li { display: flex; align-items: center; gap: 12px; padding: 10px; border-radius: 10px; background: #b1d4c317; animation: reveal .44s var(--delay) both; }
.point-icon { width: 29px; height: 29px; flex: 0 0 29px; }
.wave { display: flex; justify-content: center; align-items: center; gap: clamp(3px, .8vw, 9px); height: 92px; }
.wave i { width: 6px; height: var(--h); border-radius: 9px; background: var(--accent); opacity: .8; animation: wave-in .65s var(--delay) both; }
.dialogue { display: grid; gap: 8px; margin-top: 15px; }
.dialogue p { margin: 0; max-width: 80%; padding: 8px 12px; border-radius: 11px; background: #315548; font-size: 14px; line-height: 1.55; }
.dialogue p + p { justify-self: end; background: var(--accent); color: #153426; }
.exam-facts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 7px; margin: 16px 0 0; }
.exam-facts div { border-top: 1px solid #b8ead142; padding: 9px 0 0; }
.exam-facts dt { color: var(--muted); font-size: 13px; }
.exam-facts dd { margin: 3px 0 0; font-size: clamp(16px, 2vw, 25px); font-weight: 650; }
.navigation { flex-wrap: wrap; padding: 16px 0 26px; border-top: 1px solid #bed8cd30; }
nav, .actions { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
button { color: var(--muted); font: inherit; padding: 9px 12px; border: 1px solid transparent; border-radius: 8px; background: transparent; cursor: pointer; }
button:hover, button:focus-visible { color: var(--ink); border-color: #bdd9cd60; }
nav button[aria-current='step'], .play { background: var(--accent); color: #102e23; font-weight: 650; }
.control { border-color: #bdd9cd48; }
button:disabled { opacity: .32; cursor: default; }
.chapter-enter-active, .chapter-leave-active { transition: opacity .2s ease, transform .2s ease; }
.chapter-enter-from { opacity: 0; transform: translateY(13px); }
.chapter-leave-active { pointer-events: none; }
.chapter-leave-to { opacity: 0; transform: translateY(-6px); }
@keyframes reveal { from { opacity: 0; transform: translateY(8px); } }
@keyframes wave-in { from { transform: scaleY(.15); } }
@media (max-width: 760px) {
  .stage { grid-template-columns: 1fr; padding-block: 28px; min-height: 0; }
  .topbar { min-height: 62px; }
  .fullscreen { font-size: 13px; }
  .navigation { gap: 12px; }
  nav button { padding: 7px 8px; font-size: 13px; }
}
@media (prefers-reduced-motion: reduce) {
  .points li, .wave i { animation: none; }
  .chapter-enter-active, .chapter-leave-active { transition: none; }
}
</style>
