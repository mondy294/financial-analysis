import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 4177,
    proxy: {
      "/api": "http://[::1]:7070",
    },
  },
});
