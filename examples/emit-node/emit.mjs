#!/usr/bin/env node
// 用 Node 写出一份合规 cassette —— 不依赖 Python，不安装任何包。
// 目的：证明 docs/CASSETTE-SPEC.md 是可被第三方实现的，而不是我们的私有格式。
//
//   node examples/emit-node/emit.mjs out/
//   python tools/validate_cassette.py out/

import { createHash } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

// 规范要求：键按码点升序、逗号冒号后无空格、非 ASCII 原样输出。
function canonical(value) {
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  if (value && typeof value === "object") {
    const keys = Object.keys(value).sort();
    return "{" + keys.map((k) => JSON.stringify(k) + ":" + canonical(value[k])).join(",") + "}";
  }
  if (typeof value === "string") return JSON.stringify(value);
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  return "null";
}

function record(seq, prev, event) {
  const body = { seq, prev, event };
  const hash = createHash("sha256").update(canonical(body), "utf8").digest("hex");
  return canonical({ event, hash, prev, seq });
}

const events = [
  {
    type: "run.start",
    agent: "node-demo-agent",
    argv: ["node", "emit.mjs"],
    cwd: ".",
    env_fingerprint: "node|generic",
    t: 0.0,
  },
  { type: "model.call", model: "unknown", request: { messages: [{ role: "user", content: "fix it" }], tools: ["read_file"] }, t: 0.1 },
  {
    type: "model.result",
    text: "先看日志",
    tool_calls: [{ name: "read_file", args: { path: "logs/app.log" } }],
    usage: { in: 12, out: 8 },
    t: 0.2,
  },
  { type: "tool.call", name: "read_file", args: { path: "logs/app.log" }, t: 0.3 },
  { type: "tool.result", name: "read_file", ok: true, bytes: 66, t: 0.4 },
  { type: "run.end", exit_code: 0, files_changed: [], t: 0.5 },
];

const target = process.argv[2] || "runs/node-demo";
mkdirSync(target, { recursive: true });

let prev = null;
const lines = events.map((event, seq) => {
  const line = record(seq, prev, event);
  prev = JSON.parse(line).hash;
  return line;
});

writeFileSync(join(target, "cassette.jsonl"), lines.join("\n") + "\n", "utf8");
console.log("wrote " + lines.length + " records to " + join(target, "cassette.jsonl"));
