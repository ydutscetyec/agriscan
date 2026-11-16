import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import basicSsl from '@vitejs/plugin-basic-ssl'

/*
 * Two ways to run:
 *
 *   npm run dev          http://localhost:5173 — for the dashboard on this laptop.
 *   npm run dev:field    https://<laptop-ip>:5173 — for phones on the same Wi-Fi.
 *
 * The field mode exists because browsers only allow camera, GPS and screen wake-lock
 * on a secure (HTTPS) page. A phone opening http://192.168.x.x would have its camera
 * blocked outright. basicSsl issues a self-signed certificate; the phone shows a
 * warning once, which you accept.
 *
 * In both modes the API is reached through /api on this same server, so the browser
 * only ever talks to one origin: no CORS, and no mixed-content blocking under HTTPS.
 */
export default defineConfig(({ mode }) => {
  const field = mode === 'field'
  return {
    plugins: [react(), ...(field ? [basicSsl()] : [])],
    server: {
      port: 5173,
      host: field ? true : 'localhost',
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:5000',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
      },
    },
    test: { environment: 'node' },
  }
})
