<script setup lang="ts">
import { api } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { showFailToast, showSuccessToast } from 'vant'
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
const passwordEnabled = ref(false)
const registerEnabled = ref(false)
const tab = ref<'login' | 'register' | 'dev'>('login')
const loginForm = ref({ userid: '', password: '' })
const regForm = ref({ userid: '', name: '', department: '催收', password: '', confirm: '' })
const devForm = ref({ userid: '', name: '', department: '销售' })

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
    passwordEnabled.value = cfg.password_enabled
    registerEnabled.value = cfg.register_enabled
    qrUrl.value = cfg.qr_url
    tab.value = passwordEnabled.value ? 'login' : 'dev'
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

async function login() {
  const { userid, password } = loginForm.value
  if (!userid.trim() || !password) return showFailToast('请输入工号和密码')
  try {
    const r = await api.login(userid.trim(), password)
    finish(r.token, r.user)
  } catch (e) {
    showFailToast((e as Error).message)
  }
}

async function register() {
  const f = regForm.value
  if (!f.userid.trim() || !f.name.trim() || !f.password) return showFailToast('请填写完整信息')
  if (f.password !== f.confirm) return showFailToast('两次密码不一致')
  try {
    const r = await api.register({
      userid: f.userid.trim(),
      name: f.name.trim(),
      department: f.department,
      password: f.password,
    })
    if (r.status === 'pending') {
      showSuccessToast('注册成功，等待管理员审核')
      tab.value = 'login'
      loginForm.value.userid = f.userid.trim()
    } else if (r.token && r.user) {
      finish(r.token, r.user)
    }
  } catch (e) {
    showFailToast((e as Error).message)
  }
}

async function devLogin() {
  if (!devForm.value.userid.trim()) return showFailToast('请输入工号')
  try {
    const r = await api.devLogin(devForm.value.userid.trim(), devForm.value.name.trim(), devForm.value.department)
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
      <h1>AI 客户话术陪练</h1>
      <p class="muted">把成熟客服话术变成随时能开口练的 AI 客户</p>
    </div>

    <van-loading v-if="loading" class="center" vertical>正在登录…</van-loading>

    <template v-else>
      <van-tabs v-if="passwordEnabled || devEnabled" v-model:active="tab" type="card" style="margin: 0 12px">
        <van-tab v-if="passwordEnabled" name="login" title="账号登录" />
        <van-tab v-if="registerEnabled" name="register" title="新人注册" />
        <van-tab v-if="devEnabled" name="dev" title="开发登录" />
      </van-tabs>

      <div v-if="tab === 'login' && passwordEnabled" class="card">
        <van-cell-group inset>
          <van-field v-model="loginForm.userid" label="工号" placeholder="请输入工号" />
          <van-field v-model="loginForm.password" type="password" label="密码" placeholder="请输入密码" />
        </van-cell-group>
        <van-button type="primary" block round style="margin-top: 16px" @click="login">登录</van-button>
        <p class="muted center">忘记密码请联系管理员重置；还没有账号？去“新人注册”。</p>
      </div>

      <div v-if="tab === 'register' && registerEnabled" class="card">
        <van-cell-group inset>
          <van-field v-model="regForm.userid" label="工号" placeholder="字母/数字，如 E10001" />
          <van-field v-model="regForm.name" label="姓名" placeholder="真实姓名（管理员审核用）" />
          <van-field label="部门">
            <template #input>
              <van-radio-group v-model="regForm.department" direction="horizontal">
                <van-radio name="催收">催收</van-radio>
                <van-radio name="客服">客服</van-radio>
                <van-radio name="销售">销售</van-radio>
              </van-radio-group>
            </template>
          </van-field>
          <van-field v-model="regForm.password" type="password" label="密码" placeholder="至少 6 位" />
          <van-field v-model="regForm.confirm" type="password" label="确认密码" />
        </van-cell-group>
        <van-button type="primary" block round style="margin-top: 16px" @click="register">注册</van-button>
        <p class="muted center">注册后需管理员审核，审核通过即可登录。</p>
      </div>

      <div v-if="tab === 'dev' && devEnabled" class="card">
        <h3>开发登录</h3>
        <p class="muted">本地开发 / 演示用；生产环境关闭。</p>
        <van-cell-group inset>
          <van-field v-model="devForm.userid" label="工号" placeholder="如 E10001" />
          <van-field v-model="devForm.name" label="姓名" placeholder="选填" />
          <van-field label="部门">
            <template #input>
              <van-radio-group v-model="devForm.department" direction="horizontal">
                <van-radio name="催收">催收</van-radio>
                <van-radio name="销售">销售</van-radio>
                <van-radio name="客服">客服</van-radio>
                <van-radio name="服务">服务</van-radio>
                <van-radio name="销售">销售</van-radio>
              </van-radio-group>
            </template>
          </van-field>
        </van-cell-group>
        <van-button type="primary" block round style="margin-top: 16px" @click="devLogin">进入</van-button>
      </div>

      <div v-if="qrUrl" class="card">
        <h3>企业微信扫码登录</h3>
        <p class="muted">电脑端请使用企业微信扫码；手机端请在企业微信工作台中打开。</p>
        <van-button type="primary" block round @click="scanLogin">打开企业微信扫码</van-button>
      </div>

      <van-empty
        v-if="!qrUrl && !devEnabled && !passwordEnabled"
        :description="wecomEnabled ? '请在企业微信中打开本应用' : '登录方式未配置，请联系管理员'"
      />
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
  text-align: center;
}
</style>
