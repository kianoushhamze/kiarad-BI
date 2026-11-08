import { cp, mkdir, readdir, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const output = path.join(root, ".next", "standalone");
await stat(path.join(output, "server.js"));
await mkdir(path.join(output, ".next", "static"), { recursive: true });
await cp(path.join(root, ".next", "static"), path.join(output, ".next", "static"), { recursive: true });
await mkdir(path.join(output, "public"), { recursive: true });
for (const entry of await readdir(path.join(root, "public"), { withFileTypes: true })) {
  // Private uploads stay in backend storage and are never copied into public assets.
  if (entry.name === "uploads" || entry.isSymbolicLink() || /\.(?:bak|bafix)/i.test(entry.name)) continue;
  await cp(path.join(root, "public", entry.name), path.join(output, "public", entry.name), { recursive: true });
}
console.log("فایل‌های نمایشی نسخهٔ مستقل آماده شدند؛ پیوست‌های خصوصی کپی نشدند.");
