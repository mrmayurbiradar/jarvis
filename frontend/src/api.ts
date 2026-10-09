/**
 * Backend client for the shared frontend.
 *
 * Works identically in the browser and inside the Tauri shell: it talks to the
 * JARVIS core backend over HTTP. Native client capabilities (wake word,
 * clipboard, notifications) are exposed separately via Tauri IPC when present
 * (see `native.ts`); in a browser they are simply absent.
 */
export const API_BASE: string =
  (import.meta.env.VITE_JARVIS_API as string | undefined) ?? "http://127.0.0.1:8000";

export interface Healthz {
  status: string;
  deployment_mode: string;
}

export interface Capabilities {
  platform: string;
  deployment_mode: string;
  capabilities: Record<string, boolean>;
  mcp?: { available: boolean; tools: string[]; unavailable: string[] };
}

export interface WorkflowHealth {
  status: string;
  engine: string;
  scheduler_thread?: boolean | string;
  enabled?: number;
  total?: number;
  workflow_ids?: string[];
  last_error?: string;
}

export interface PairRequest {
  pairing_id: string;
  code: string;
  expires_at: string;
  verification_uri: string;
}

export interface ChatResponse {
  session_id: string;
  text: string;
  tool_calls: number;
}

export interface AuditEntry {
  ts: string;
  actor: string;
  capability: string;
  target: string;
  decision: string;
  outcome: string;
  reason: string;
}

export interface Approval {
  id: string;
  session_id: string;
  capability: string;
  target: Record<string, unknown>;
  status: string;
  created_at: string;
}

export interface RespondResult {
  id: string;
  status: string;
  result: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.name = "ApiError";
  }
}

export class JarvisApi {
  constructor(
    readonly base: string = API_BASE,
    private token: string = "",
  ) {}

  setToken(token: string): void {
    this.token = token;
  }

  get hasToken(): boolean {
    return this.token !== "";
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
    };
    const resp = await fetch(`${this.base}${path}`, { ...init, headers });
    if (!resp.ok) {
      let detail: unknown;
      try {
        detail = await resp.json();
      } catch {
        detail = resp.statusText;
      }
      throw new ApiError(resp.status, detail);
    }
    return resp.json() as Promise<T>;
  }

  healthz(): Promise<Healthz> {
    return this.request<Healthz>("/healthz");
  }

  capabilities(): Promise<Capabilities> {
    return this.request<Capabilities>("/api/capabilities");
  }

  requestPairing(displayName: string): Promise<PairRequest> {
    return this.request<PairRequest>("/api/pair/request", {
      method: "POST",
      body: JSON.stringify({ display_name: displayName }),
    });
  }

  confirmPairing(code: string): Promise<{ token: string; expires_in: number }> {
    return this.request<{ token: string; expires_in: number }>("/api/pair/confirm", {
      method: "POST",
      body: JSON.stringify({ code }),
    });
  }

  chat(message: string, sessionId?: string): Promise<ChatResponse> {
    return this.request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message, session_id: sessionId }),
    });
  }

  audit(limit = 100): Promise<AuditEntry[]> {
    return this.request<AuditEntry[]>(`/api/audit?limit=${limit}`);
  }

  workflowHealth(): Promise<WorkflowHealth> {
    return this.request<WorkflowHealth>("/api/workflow/health");
  }

  pendingApprovals(): Promise<Approval[]> {
    return this.request<Approval[]>("/api/approvals/pending");
  }

  respondApproval(id: string, decision: "approve" | "deny"): Promise<RespondResult> {
    return this.request<RespondResult>(`/api/approvals/${id}/respond`, {
      method: "POST",
      body: JSON.stringify({ decision }),
    });
  }
}