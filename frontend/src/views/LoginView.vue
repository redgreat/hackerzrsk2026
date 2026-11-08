<script setup lang="ts">
import { api } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { showFailToast } from 'vant'
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const REDIRECT_KEY = 'coach_redirect'
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const loading = ref(true)
const devEnabled = ref(false)
const wecomEnabled = ref(false)
const qrUrl = ref<string | null>(null)
const form = ref({ userid: '', name: '', department: '销售' })

function finish(token: string, user: Parameters<typeof auth.setLogin>[1]) {
  auth.setLogin(token, user)
  const target = (route.query.redirect as string) || sessionStorage.getItem(REDIRECT_KEY) || '/'
  sessionStorage.removeItem(REDIRECT_KEY)
  router.replace(target)
}

onMounted(async () => {
  try {
    const code = route.query.code as string | undefined
    if (code) {
      const r = await api.wecomLogin(code)
      return finish(r.token, r.user)
    }
    const cfg = await api.authConfig(`${location.origin}/login`)
    wecomEnabled.value = cfg.wecom_enabled
    devEnabled.value = cfg.dev_login_enabled
    qrUrl.value = cfg.qr_url
    if (cfg.oauth_url && /wxwork/i.test(navigator.userAgent)) {
      sessionStorage.setItem(REDIRECT_KEY, (route.query.redirect as string) || '/')
      location.replace(cfg.oauth_url)
      return
    }
  } catch (e) {
    showFailToast((e as Error).message)
  }
  loading.value = false
})

function scanLogin() {
  sessionStorage.setItem(REDIRECT_KEY, (route.query.redirect as string) || '/')
  location.href = qrUrl.value!
}

async function devLogin() {
  if (!form.value.userid.trim()) return showFailToast('请输入工号')
  try {
    const r = await api.devLogin(form.value.userid.trim(), form.value.name.trim(), form.value.department)
    finish(r.token, r.user)
  } catch (e) {
    showFailToast((e as Error).message)
  }
}
</script>

<template>
  <div class="login">
    <div class="brand">
      <div class="logo">练</div>
      <h1>AI 客户陪练</h1>
      <p class="muted">24 小时在线、不嫌烦、按销冠标准打分的陪练客户</p>
    </div>

    <van-loading v-if="loading" class="center" vertical>正在登录…</van-loading>

    <template v-else>
      <div v-if="qrUrl" class="card">
        <h3>企业微信扫码登录</h3>
        <p class="muted">电脑端请使用企业微信扫码；手机端请在企业微信工作台中打开。</p>
        <van-button type="primary" block round @click="scanLogin">打开企业微信扫码</van-button>
      </div>

      <div v-if="devEnabled" class="card">
        <h3>开发登录</h3>
        <p class="muted">本地开发 / 演示用；生产环境关闭。</p>
        <van-cell-group inset>
          <van-field v-model="form.userid" label="工号" placeholder="如 E10001" />
          <van-field v-model="form.name" label="姓名" placeholder="选填" />
          <van-field label="部门">
            <template #input>
              <van-radio-group v-model="form.department" direction="horizontal">
                <van-radio name="销售">销售</van-radio>
                <van-radio name="客服">客服</van-radio>
              </van-radio-group>
            </template>
          </van-field>
        </van-cell-group>
        <van-button type="primary" block round style="margin-top: 16px" @click="devLogin">进入</van-button>
      </div>

      <van-empty v-if="!qrUrl && !devEnabled" :description="wecomEnabled ? '请在企业微信中打开本应用' : '登录方式未配置，请联系管理员'" />
    </template>
  </div>
</template>

<style scoped>
.login {
  min-height: 100vh;
  padding-top: 12vh;
  box-sizing: border-box;
}
.brand {
  text-align: center;
  margin-bottom: 24px;
}
.brand h1 {
  margin: 12px 0 6px;
  font-size: 24px;
}
.logo {
  width: 64px;
  height: 64px;
  margin: 0 auto;
  border-radius: 18px;
  background: linear-gradient(135deg, #1f6feb, #6aa6ff);
  color: #fff;
  font-size: 32px;
  line-height: 64px;
  font-weight: 600;
}
.center {
  margin-top: 40px;
}
</style>
