import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      "/api/registry": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/registry/, ""),
      },
      "/api/coordinator": {
        target: "http://localhost:8001",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/coordinator/, ""),
      },
      "/api/procurement": {
        target: "http://localhost:8010",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/procurement/, ""),
      },
      "/ws": {
        target: "ws://localhost:8001",
        ws: true,
      },
    },
  },
});
