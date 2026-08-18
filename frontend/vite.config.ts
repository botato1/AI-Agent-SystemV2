import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// VITE_API_URL을 비워두고(.env) 프론트는 항상 상대경로(/api/...)로만 요청하게 만든 다음,
// 실제 백엔드로는 여기 서버(Vite Node 프로세스)가 대신 전달한다.
// 브라우저는 계속 같은 오리진(localhost:5173)만 보게 되므로 CORS 자체가 발생하지 않는다 —
// 백엔드가 Access-Control-Allow-Origin 헤더를 안 내려줘도 개발 중엔 문제없이 동작함.
//
// (HTTPS(basicSsl) 시도했다가 되돌림 - Vite HTTPS 개발서버가 일반 HTTP 백엔드로
// 웹소켓을 프록시할 때 TLSWrap ECONNRESET이 반복 발생하는 호환성 문제가 있어서,
// 팀원 마이크 권한은 크롬 플래그(unsafely-treat-insecure-origin-as-secure)로 대신 처리한다.)
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backendTarget = env.API_PROXY_TARGET || 'http://localhost:8000'

  return {
    plugins: [react()],
    server: {
      host: true, // 127.0.0.1, localhost, 내부 IP 등 모든 호스트 접근 허용
      port: 5173,
      proxy: {
        '/api': {
          target: backendTarget,
          changeOrigin: true,
          ws: true, // 실시간 회의 WebSocket(/api/workspaces/.../stream)도 같이 프록시
        },
      },
    },
  }
})