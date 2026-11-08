import { api } from '@/api'
import { tokenStore } from '@/api/http'
import type { User } from '@/types'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(tokenStore.get())
  const user = ref<User | null>(null)
  const loggedIn = computed(() => !!token.value)

  function setLogin(t: string, u: User) {
    tokenStore.set(t)
    token.value = t
    user.value = u
  }

  async function loadMe() {
    if (token.value && !user.value) user.value = await api.me()
  }

  function logout() {
    tokenStore.clear()
    token.value = null
    user.value = null
  }

  return { token, user, loggedIn, setLogin, loadMe, logout }
})
