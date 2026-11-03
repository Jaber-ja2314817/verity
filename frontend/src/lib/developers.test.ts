import { describe, expect, it } from "vitest";
import { adminErrorMessage, checkExample, usageExample } from "./developers";

describe("checkExample", () => {
  it("builds a curl command for POST /v1/checks with the key in the header", () => {
    const cmd = checkExample("https://verity.example", "Water boils at 100C.", "vrt_abc");
    expect(cmd).toContain('curl -X POST "https://verity.example/v1/checks?wait=true"');
    expect(cmd).toContain("Authorization: Bearer vrt_abc");
    expect(cmd).toContain('"text":"Water boils at 100C."');
  });
  it("escapes single quotes so the shell command stays valid", () => {
    expect(checkExample("https://v.example", "It's true.")).toContain("It'\\''s true.");
  });
  it("uses a placeholder key by default", () => {
    expect(checkExample("https://v.example", "x")).toContain("vrt_YOUR_KEY");
    expect(usageExample("https://v.example")).toContain("https://v.example/v1/usage");
  });
});

describe("adminErrorMessage", () => {
  it("explains the statuses the admin endpoints return", () => {
    expect(adminErrorMessage(401, "x")).toMatch(/Wrong admin secret/);
    expect(adminErrorMessage(404, "x")).toMatch(/turned off/);
    expect(adminErrorMessage(429, "x")).toMatch(/Too many/);
    expect(adminErrorMessage(500, "boom")).toBe("boom");
  });
});
