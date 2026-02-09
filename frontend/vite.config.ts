import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";

// Base path for production deployment (e.g., "/iv" for yourdomain.com/iv/)
// Set via environment variable or default to "/" for local dev
const basePath = process.env.VITE_BASE_PATH || "/";

export default defineConfig({
  base: basePath,
  plugins: [vue(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8080",
        changeOrigin: true,
        cookieDomainRewrite: "",
        ws: true,
      },
      "/auth": {
        target: "http://127.0.0.1:8080",
        changeOrigin: true,
        cookieDomainRewrite: "",
      },
    },
  },
  build: {
    outDir: "../web/static",
    emptyOutDir: true,
  },
});
