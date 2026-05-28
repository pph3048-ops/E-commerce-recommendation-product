import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api':           'http://localhost:5000',
      '/search':        'http://localhost:5000',
      '/recommend':     'http://localhost:5000',
      '/trending':      'http://localhost:5000',
      '/top-rated':     'http://localhost:5000',
      '/wishlist':      'http://localhost:5000',
      '/interact':      'http://localhost:5000',
      '/user_purchases':'http://localhost:5000',
      '/products':           'http://localhost:5000',
      '/product/':           'http://localhost:5000',
      '/recently-viewed/':   'http://localhost:5000',
      '/because-you-bought/':'http://localhost:5000',
      '/cart/':              'http://localhost:5000',
      '/logout':             'http://localhost:5000',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
