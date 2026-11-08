import { VantResolver } from '@vant/auto-import-resolver'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import Components from 'unplugin-vue-components/vite'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue(), Components({ resolvers: [VantResolver()], dts: 'src/components.d.ts' })],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  build: { chunkSizeWarningLimit: 800 },
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': { target: process.env.API_TARGET ?? 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
