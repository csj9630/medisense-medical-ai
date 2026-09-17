import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  // Backend와 Frontend가 프로젝트 최상위 .env 하나를 공유합니다.
  // 브라우저에는 VITE_ 접두사 변수만 노출됩니다.
  envDir: '..',
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api/v1': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
