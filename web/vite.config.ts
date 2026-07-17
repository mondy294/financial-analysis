import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

const apiProxy = process.env.VITE_API_PROXY || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: apiProxy,
        changeOrigin: true,
      },
    },
  },
});
