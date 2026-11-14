import { describe, expect, it } from "vitest";
import fixtures from "../../../protocol/fixtures.json";
import { validateFrame } from "./protocol";

describe("bridge contract fixtures", () => {
  it("accepts matching frames", () => {
    for (const frame of fixtures.valid) expect(validateFrame(JSON.stringify(frame))).toEqual(frame);
  });
  it("rejects invalid versions, operations, and DTOs", () => {
    for (const frame of fixtures.invalid) expect(() => validateFrame(JSON.stringify(frame))).toThrow();
  });
  it("rejects malformed and oversized frames", () => {
    expect(() => validateFrame(fixtures.malformed)).toThrow();
    expect(() => validateFrame("x".repeat(1_048_577))).toThrow("FRAME_TOO_LARGE");
  });
});
