/**
 * Ensure pi-native workspace layout under EYOT_WORKSPACE_PATH (/data):
 *   .pi/  work/  memory/  shared/
 * and materialize agent SYSTEM.md from ConfigMap (/etc/config).
 */

import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const CONFIG_DIR = process.env.EYOT_AGENT_CONFIG_DIR?.trim() || "/etc/config";

export function ensureWorkspaceLayout(root: string): void {
  for (const rel of ["work", "memory", ".pi", "shared", path.join(".pi", "skills")]) {
    const p = path.join(root, rel);
    fs.mkdirSync(p, { recursive: true });
  }
}

function copyIfPresent(src: string, dest: string): boolean {
  if (!fs.existsSync(src)) return false;
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.copyFileSync(src, dest);
  return true;
}

export function materializeAgentBundle(root: string, log: (m: string, ...a: unknown[]) => void): void {
  ensureWorkspaceLayout(root);

  const systemSrc = path.join(CONFIG_DIR, "SYSTEM.md");
  const agentsSrc = path.join(CONFIG_DIR, "AGENTS.md");
  const settingsSrc = path.join(CONFIG_DIR, "settings.json");
  const globalSrc = path.join(CONFIG_DIR, "global-settings.json");

  const wroteSystem = copyIfPresent(systemSrc, path.join(root, ".pi", "SYSTEM.md"));
  const wroteAgents = copyIfPresent(agentsSrc, path.join(root, "AGENTS.md"));
  const wroteSettings = copyIfPresent(settingsSrc, path.join(root, ".pi", "settings.json"));

  const agentDir = path.join(os.homedir(), ".pi", "agent");
  fs.mkdirSync(agentDir, { recursive: true });
  if (fs.existsSync(globalSrc)) {
    fs.copyFileSync(globalSrc, path.join(agentDir, "settings.json"));
  } else {
    fs.writeFileSync(
      path.join(agentDir, "settings.json"),
      JSON.stringify({ defaultProjectTrust: "always" }, null, 2) + "\n",
      "utf8",
    );
  }

  // Fallback stub if deploy did not ship SYSTEM.md yet.
  const systemDest = path.join(root, ".pi", "SYSTEM.md");
  if (!fs.existsSync(systemDest)) {
    const slug = process.env.EYOT_INSTANCE_ID || "instance";
    fs.writeFileSync(
      systemDest,
      `# Identity\n\nYou are Eyot Lost One instance ${slug}.\n`,
      "utf8",
    );
  }

  log("workspace layout ready", {
    root,
    system: wroteSystem || fs.existsSync(systemDest),
    agents: wroteAgents,
    settings: wroteSettings,
    dirs: ["work", "memory", ".pi", "shared"].filter((d) =>
      fs.existsSync(path.join(root, d)),
    ),
  });
}
