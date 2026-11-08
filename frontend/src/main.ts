import { createPinia } from 'pinia'
import 'vant/es/dialog/style'
import 'vant/es/notify/style'
import 'vant/es/toast/style'
import { createApp } from 'vue'
import { setUnauthorizedHandler } from './api/http'
import App from './App.vue'
import router from './router'
import './styles.css'

setUnauthorizedHandler(() => {
  if (router.currentRoute.value.name !== 'login') {
    router.replace({ name: 'login', query: { redirect: router.currentRoute.value.fullPath } })
  }
})

createApp(App).use(createPinia()).use(router).mount('#app')
