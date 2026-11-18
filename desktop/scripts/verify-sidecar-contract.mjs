import { spawnSync } from "node:child_process";
import { readFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const desktop = dirname(dirname(fileURLToPath(import.meta.url)));
const executable = join(desktop, "src-tauri", "binaries", "fahmm-sidecar-x86_64-pc-windows-msvc.exe");
const contract = JSON.parse(readFileSync(join(desktop, "protocol", "contract.json"), "utf8"));
const temporaryData = mkdtempSync(join(tmpdir(), "fahmm-contract-"));

try {
  const request = JSON.stringify({
    v: contract.version,
    kind: "request",
    id: "build-contract-check",
    op: "session.hello",
    params: { versions: [contract.version] },
  });
  const child = spawnSync(executable, [], {
    input: `${request}\n`, encoding: "utf8", timeout: 30000,
    env: { ...process.env, LOCALAPPDATA: temporaryData },
  });
  if (child.status !== 0) {
    throw new Error("Bundled sidecar could not start. Rebuild it with python scripts/build_sidecar.py.");
  }
  const reply = JSON.parse(child.stdout.trim().split(/\r?\n/)[0]);
  const capabilities = reply.result?.capabilities;
  if (reply.kind !== "response" || !Array.isArray(capabilities)) {
    throw new Error("Bundled sidecar did not return its capabilities.");
  }
  const expected = Object.keys(contract.operations);
  const missing = expected.filter((operation) => !capabilities.includes(operation));
  const unexpected = capabilities.filter((operation) => !expected.includes(operation));
  if (missing.length || unexpected.length) {
    throw new Error(`Bundled sidecar contract mismatch (missing: ${missing.join(", ") || "none"}; unexpected: ${unexpected.join(", ") || "none"}). Rebuild the sidecar before building Tauri.`);
  }
  console.log(`Bundled sidecar contract verified (${expected.length} operations).`);
} finally {
  rmSync(temporaryData, { recursive: true, force: true });
}
