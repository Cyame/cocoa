/**
 * Spawn `pi --mode rpc` and speak JSONL over stdin/stdout.
 * Framing: split ONLY on `\n` (do not use Node readline).
 */

import { type ChildProcessWithoutNullStreams, spawn } from "node:child_process";
import { EventEmitter } from "node:events";

export type PiEvent = Record<string, unknown> & { type?: string };

export interface PiRpcOptions {
  piBin?: string;
  cwd?: string;
  env?: NodeJS.ProcessEnv;
  extraArgs?: string[];
  log?: (msg: string, ...args: unknown[]) => void;
}

export class PiRpc extends EventEmitter {
  private child: ChildProcessWithoutNullStreams | null = null;
  private buffer = "";
  private readonly opts: PiRpcOptions;
  private readonly log: (msg: string, ...args: unknown[]) => void;
  private started = false;

  constructor(opts: PiRpcOptions = {}) {
    super();
    this.opts = opts;
    this.log = opts.log ?? ((m, ...a) => console.log(`[pi-rpc] ${m}`, ...a));
  }

  start(): void {
    if (this.started) return;
    this.started = true;
    const bin = this.opts.piBin ?? process.env.PI_BIN ?? "pi";
    const args = ["--mode", "rpc", "--no-session", ...(this.opts.extraArgs ?? [])];
    const model = process.env.PI_MODEL?.trim();
    if (model) {
      args.push("--model", model);
    }
    const provider = process.env.PI_PROVIDER?.trim();
    if (provider) {
      args.push("--provider", provider);
    }

    this.log("spawn", bin, args.join(" "));
    this.child = spawn(bin, args, {
      cwd: this.opts.cwd,
      env: { ...process.env, ...this.opts.env },
      stdio: ["pipe", "pipe", "pipe"],
    });

    this.child.stdout.on("data", (chunk: Buffer) => {
      this.buffer += chunk.toString("utf8");
      this.drain();
    });
    this.child.stderr.on("data", (chunk: Buffer) => {
      this.log("stderr", chunk.toString("utf8").trim());
    });
    this.child.on("exit", (code, signal) => {
      this.log("exit", code, signal);
      this.child = null;
      this.started = false;
      this.emit("exit", code, signal);
    });
    this.child.on("error", (err) => {
      this.log("spawn error", err.message);
      this.emit("error", err);
    });
  }

  private drain(): void {
    while (true) {
      const idx = this.buffer.indexOf("\n");
      if (idx < 0) break;
      let line = this.buffer.slice(0, idx);
      this.buffer = this.buffer.slice(idx + 1);
      if (line.endsWith("\r")) line = line.slice(0, -1);
      if (!line.trim()) continue;
      try {
        const evt = JSON.parse(line) as PiEvent;
        this.emit("event", evt);
      } catch (err) {
        this.log("bad jsonl", line.slice(0, 200), err);
      }
    }
  }

  send(cmd: Record<string, unknown>): boolean {
    if (!this.child?.stdin.writable) return false;
    this.child.stdin.write(`${JSON.stringify(cmd)}\n`);
    return true;
  }

  prompt(message: string, id?: string): boolean {
    return this.send({
      id: id ?? crypto.randomUUID(),
      type: "prompt",
      message,
    });
  }

  abort(): boolean {
    return this.send({ type: "abort" });
  }

  kill(): void {
    if (!this.child) return;
    try {
      this.child.kill("SIGTERM");
    } catch {
      /* ignore */
    }
    this.child = null;
    this.started = false;
  }

  get running(): boolean {
    return this.child !== null;
  }
}
