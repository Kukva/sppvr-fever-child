import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000', // Исправлен порт на 8000
        changeOrigin: true,
        ws: true, // Включаем WebSocket для API эндпоинтов
      },
      '/ws': {
        target: 'ws://localhost:8000', // Исправлен порт на 8000
        ws: true,
      },
    },
  },
  define: {
    // В production не устанавливаем VITE_API_BASE_URL, чтобы использовать относительные пути
    // В development значения устанавливаются через .env файл или используются значения по умолчанию
    // 'import.meta.env.VITE_API_BASE_URL': JSON.stringify('http://localhost:8000'), // Убрано для production
    'import.meta.env.VITE_WS_URL': JSON.stringify('ws://localhost:8000'),
  },
})
