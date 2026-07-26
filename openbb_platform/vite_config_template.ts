import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: 'localhost',
    
    // ============================================================
    // PROXY CONFIGURATION
    // This forwards API calls from React to the FastAPI backend
    // ============================================================
    proxy: {
      // Forward all /api/* requests to FastAPI backend
      '/api': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path, // Keep the path as-is
        logLevel: 'debug', // Show proxy logs
      },
    },

    // ============================================================
    // CORS & SECURITY
    // ============================================================
    cors: true,
    
    // Middleware to set custom headers
    middlewareMode: false,
  },

  // ============================================================
  // BUILD CONFIGURATION
  // ============================================================
  build: {
    outDir: 'dist',
    sourcemap: true,
    minify: 'terser',
    target: 'esnext',
    
    // Optimize large chunks
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor': [
            'react',
            'react-dom',
            'axios',
            '@tanstack/react-query',
          ],
        },
      },
    },
  },

  // ============================================================
  // ENVIRONMENT VARIABLES
  // ============================================================
  define: {
    __API_URL__: JSON.stringify(process.env.VITE_API_URL || 'http://localhost:8000'),
  },

  // ============================================================
  // OPTIMIZATIONS
  // ============================================================
  optimizeDeps: {
    include: ['react', 'react-dom', 'axios'],
  },
})
