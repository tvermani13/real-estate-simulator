import { fileURLToPath } from "url";

const turbopackRoot = fileURLToPath(new URL(".", import.meta.url));

/** @type {import("next").NextConfig} */
const nextConfig = {
  turbopack: {
    // Force Turbopack to treat `frontend/` as the workspace root so module
    // resolution (e.g. tailwindcss) uses `frontend/node_modules`.
    root: turbopackRoot,
  },
};

export default nextConfig;

