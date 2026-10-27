import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig(({ mode }) => {
  const base = loadEnv(mode, ".", "PAGES_").PAGES_BASE_PATH || "/Ankara-Hastane-Yerlestirme/";
  if (mode === "pages" && !/^\/(?:[A-Za-z0-9_-]+\/)?$/.test(base)) throw Error("Geçersiz Pages proje yolu");
  return {
  plugins: [react()],
  base: mode === "pages" ? base : "/",
  publicDir: mode === "pages" ? "work/pages-public/site" : false,
  build: { outDir: mode === "pages" ? "dist-pages" : "dist" },
  preview: { proxy: {} },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
  };
});
