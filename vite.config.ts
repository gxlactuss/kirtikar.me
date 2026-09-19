import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Apex custom domain (kirtikar.me) serves from the root, so base is '/'.
// Using '/kirtikar/' here would break every asset URL on the live site.
export default defineConfig({
  base: '/',
  plugins: [react()],
  server: {
    // 5173 is already in the backend's CORS_ORIGINS. Fail rather than
    // silently hop to 5174, which would be a cross-origin surprise.
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
});
