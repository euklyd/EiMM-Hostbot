import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8080",
        changeOrigin: true,
        cookieDomainRewrite: "localhost",
        ws: true,
      },
      "/auth": {
        target: "http://localhost:8080",
        changeOrigin: true,
        cookieDomainRewrite: "localhost",
      },
    },
  },
  build: {
    outDir: "../web/static",
    emptyOutDir: true,
  },
});
