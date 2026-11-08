<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const showTab = computed(() => !!route.meta.tab)
</script>

<template>
  <router-view />
  <van-tabbar v-if="showTab" route safe-area-inset-bottom>
    <van-tabbar-item to="/" icon="fire-o">练习</van-tabbar-item>
    <van-tabbar-item to="/history" icon="chart-trending-o">我的</van-tabbar-item>
  </van-tabbar>
</template>
