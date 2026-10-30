// 跨平台调用 scripts/subset-genryu.py。
// 找不到带 fontTools + brotli 的 Python 时只警告、不失败：
// 部署会沿用 static/fonts 里已提交的子集，站点照常上线。
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const script = path.join(here, "subset-genryu.py");
const args = process.argv.slice(2);
const checkOnly = args.includes("--check");

// Windows 上通常只有 python / py；Linux（Netlify）上是 python3
const candidates = process.platform === "win32" ? ["python", "py"] : ["python3", "python"];

const hasFontTools = (exe) =>
  spawnSync(exe, ["-c", "import fontTools, brotli"], { stdio: "ignore" }).status === 0;

for (const exe of candidates) {
  if (!hasFontTools(exe)) continue;
  const run = spawnSync(exe, [script, ...args], { stdio: "inherit" });
  process.exit(run.status ?? 1);
}

const msg = "[fonts] 没找到带 fontTools+brotli 的 Python，跳过子集化，沿用已提交的子集。";
if (checkOnly) {
  console.error(msg);
  process.exit(1);
}
console.warn(msg);
process.exit(0);
