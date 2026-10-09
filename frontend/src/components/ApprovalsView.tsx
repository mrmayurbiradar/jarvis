import { useCallback, useEffect, useState } from "react";
import { Approval, JarvisApi } from "../api";

interface Props {
  api: JarvisApi;
  /** Called after an approval is resolved so the tab badge can refresh. */
  onChanged?: () => void;
}

export function ApprovalsView({ api, onChanged }: Props) {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api
      .pendingApprovals()
      .then(setApprovals)
      .catch((e) => setError(String(e)));
  }, [api]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000); // poll — a scheduler job may queue new ones
    return () => clearInterval(t);
  }, [refresh]);

  const respond = (a: Approval, decision: "approve" | "deny") => {
    setBusy(a.id);
    setError(null);
    setNotice(null);
    api
      .respondApproval(a.id, decision)
      .then((r) => {
        setNotice(
          r.status === "approved"
            ? `Approved — result: ${r.result || "(no output)"}`
            : "Denied — the action was not executed.",
        );
        onChanged?.();
        refresh();
      })
      .catch((e) => setError(String(e)))
      .finally(() => setBusy(null));
  };

  const targetText = (a: Approval): string => {
    try {
      return JSON.stringify(a.target);
    } catch {
      return String(a.target);
    }
  };

  return (
    <div className="panel">
      <h2>Approvals</h2>
      <p className="muted">
        High-risk actions (shell, workflow runs) wait for your OK before they
        execute — this is security gate 3 of ADR-0005.
      </p>
      {error && <div className="error">{error}</div>}
      {notice && <div className="notice">{notice}</div>}

      {approvals.length === 0 && (
        <div className="muted">Nothing waiting for approval right now.</div>
      )}

      {approvals.map((a) => (
        <div className="approval-card" key={a.id}>
          <div className="approval-head">
            <span className={`chip ${a.capability.startsWith("shell") ? "chip-risk" : ""}`}>
              {a.capability}
            </span>
            <span className="mono muted">{a.created_at.replace("T", " ").slice(0, 19)}</span>
          </div>
          <div className="approval-target mono">{targetText(a)}</div>
          <div className="approval-actions">
            <button
              className="btn-approve"
              disabled={busy === a.id}
              onClick={() => respond(a, "approve")}
            >
              {busy === a.id ? "Running…" : "Approve"}
            </button>
            <button
              className="btn-deny"
              disabled={busy === a.id}
              onClick={() => respond(a, "deny")}
            >
              Deny
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}