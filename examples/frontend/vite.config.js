import { readFileSync } from "node:fs";
import { defineConfig } from "vite";

export default defineConfig(({ command }) => ({
  server: command === "serve" ? {
    host: "totalis.localhost",
    port: 3443,
    strictPort: true,
    https: {
      key: readFileSync(new URL("./certs/dev-key.pem", import.meta.url)),
      cert: readFileSync(new URL("./certs/dev.pem", import.meta.url)),
    },
  } : undefined,
}));
