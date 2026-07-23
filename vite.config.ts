import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // 127.0.0.1, localhost, 내부 IP 등 모든 호스트 접근 허용
    port: 5173,
  }
})