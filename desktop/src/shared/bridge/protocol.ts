import contract from "../../../protocol/contract.json";

export type RequestFrame = { v: number; kind: "request"; id: string; op: string; params: Record<string, unknown> };
export type ResponseFrame = { v: number; kind: "response"; id: string; op: string; result: Record<string, unknown> };
export type ErrorFrame = { v: number; kind: "error"; id: string; error: { code: string; message: string } };
export type EventFrame = { v: number; kind: "event"; event: string; jobId?: string; data: Record<string, unknown> };
export type Frame = RequestFrame | ResponseFrame | ErrorFrame | EventFrame;

export type HelloParams = { versions: number[] };
export type HelloResult = { selectedVersion: number; capabilities: string[] };
export type HealthResult = { status: string };

const idPattern = new RegExp(contract.requestIdPattern);
const operations = contract.operations as Record<string, { params: Record<string, string>; result: Record<string, string> }>;
const events = contract.events as Record<string, Record<string, string>>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function fieldsMatch(value: unknown, fields: Record<string, string>): value is Record<string, unknown> {
  if (!isRecord(value)) return false;
  return Object.entries(fields).every(([name, type]) => {
    const item = value[name];
    switch (type) {
      case "string": return typeof item === "string";
      case "string?": return item === null || typeof item === "string";
      case "number": return typeof item === "number" && Number.isFinite(item);
      case "number?": return item === null || (typeof item === "number" && Number.isFinite(item));
      case "integer": return Number.isInteger(item);
      case "boolean": return typeof item === "boolean";
      case "string[]": return Array.isArray(item) && item.every((part) => typeof part === "string");
      case "integer[]": return Array.isArray(item) && item.every((part) => Number.isInteger(part));
      case "number[]": return Array.isArray(item) && item.every((part) => typeof part === "number" && Number.isFinite(part));
      case "object": return isRecord(item);
      case "object?": return item === null || isRecord(item);
      case "object[]": return Array.isArray(item) && item.every(isRecord);
      default: return false;
    }
  });
}

export function validateFrame(raw: string): Frame {
  if (new TextEncoder().encode(raw).length > contract.maxFrameBytes) throw new Error("FRAME_TOO_LARGE");
  let value: unknown;
  try { value = JSON.parse(raw); } catch { throw new Error("MALFORMED_FRAME"); }
  if (!isRecord(value) || value.v !== contract.version) throw new Error("UNSUPPORTED_VERSION");
  const idOk = typeof value.id === "string" && idPattern.test(value.id);
  switch (value.kind) {
    case "request":
      if (!idOk || typeof value.op !== "string" || !operations[value.op] || !fieldsMatch(value.params, operations[value.op].params)) break;
      return value as RequestFrame;
    case "response":
      if (!idOk || typeof value.op !== "string" || !operations[value.op] || !fieldsMatch(value.result, operations[value.op].result)) break;
      return value as ResponseFrame;
    case "error":
      if (!idOk || !isRecord(value.error) || typeof value.error.code !== "string" || !contract.errorCodes.includes(value.error.code) || typeof value.error.message !== "string" || value.error.message.length > 200) break;
      return value as ErrorFrame;
    case "event":
      if (typeof value.event !== "string" || !events[value.event] || (value.jobId !== undefined && (typeof value.jobId !== "string" || !idPattern.test(value.jobId))) || !fieldsMatch(value.data, events[value.event])) break;
      return value as EventFrame;
  }
  throw new Error("INVALID_FRAME");
}
