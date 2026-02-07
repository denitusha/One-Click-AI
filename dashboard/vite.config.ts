import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 3000,
    proxy: {
      "/api/index": {
        target: "http://localhost:6900",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/index/, ""),
      },
      "/api/procurement": {
        target: "http://localhost:6010",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/procurement/, ""),
      },
    },
  },
});
