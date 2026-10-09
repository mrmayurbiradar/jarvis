import { describe, expect, it, vi, beforeEach } from "vitest";
import { ApiError, JarvisApi } from "./api";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("JarvisApi", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("sends pairing request and confirm flow", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ code: "123456", pairing_id: "p1", expires_at: "x", verification_uri: "/" }))
      .mockResolvedValueOnce(jsonResponse({ token: "tok-abc", expires_in: 600 }));
    const api = new JarvisApi("http://test");
    const req = await api.requestPairing("demo");
    expect(req.code).toBe("123456");
    const conf = await api.confirmPairing("123456");
    expect(conf.token).toBe("tok-abc");
    // token now set — subsequent requests carry the bearer header
    api.setToken(conf.token);
    expect(fetchMock.mock.calls[1][1]?.body).toBe(JSON.stringify({ code: "123456" }));
  });

  it("sends Authorization header once token is set", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ ok: true }));
    const api = new JarvisApi("http://test");
    api.setToken("tok-xyz");
    await api.chat("hi");
    const [, init] = fetchMock.mock.calls[0];
    expect((init?.headers as Record<string, string>).Authorization).toBe("Bearer tok-xyz");
  });

  it("throws ApiError with detail on non-2xx", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ detail: "invalid or expired pairing code" }, 404),
    );
    const api = new JarvisApi("http://test");
    const err = await api.confirmPairing("000000").then(
      () => null,
      (e: unknown) => e,
    );
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(404);
    expect((err as ApiError).message).toContain("invalid or expired");
  });

  it("builds correct query for audit", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse([]));
    const api = new JarvisApi("http://test");
    await api.audit(25);
    expect(fetchMock.mock.calls[0][0]).toBe("http://test/api/audit?limit=25");
  });

  it("lists pending approvals", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        jsonResponse([
          {
            id: "a1",
            session_id: "s1",
            capability: "shell.run",
            target: { command: "echo hi" },
            status: "pending",
            created_at: "x",
          },
        ]),
      );
    const api = new JarvisApi("http://test");
    const rows = await api.pendingApprovals();
    expect(fetchMock.mock.calls[0][0]).toBe("http://test/api/approvals/pending");
    expect(rows[0].capability).toBe("shell.run");
    expect(rows[0].target).toEqual({ command: "echo hi" });
  });

  it("posts an approval decision to respond", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ id: "a1", status: "approved", result: "ok" }));
    const api = new JarvisApi("http://test");
    const res = await api.respondApproval("a1", "approve");
    expect(res.status).toBe("approved");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://test/api/approvals/a1/respond");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ decision: "approve" }));
  });
});