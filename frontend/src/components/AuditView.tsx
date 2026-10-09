import { useEffect, useState } from "react";
import { AuditEntry, JarvisApi } from "../api";

interface Props {
  api: JarvisApi;
}

const DECISION_CLASS: Record<string, string> = {
  allow: "ok",
  deny: "no",
};

export function AuditView({ api }: Props) {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .audit()
      .then(setEntries)
      .catch((e) => setError(String(e)));
  }, [api]);

  return (
    <div className="panel">
      <h2>Audit log</h2>
      <p className="muted">Every computer operation, whether allowed or denied.</p>
      {error && <div className="error">{error}</div>}
      <table>
        <thead>
          <tr><th>When</th><th>Actor</th><th>Capability</th><th>Target</th><th>Decision</th><th>Outcome</th></tr>
        </thead>
        <tbody>
          {entries.map((e, i) => (
            <tr key={i}>
              <td className="mono">{e.ts.replace("T", " ").slice(0, 19)}</td>
              <td>{e.actor}</td>
              <td>{e.capability}</td>
              <td className="mono">{e.target}</td>
              <td className={DECISION_CLASS[e.decision] ?? ""}>{e.decision}</td>
              <td>{e.outcome}{e.reason ? ` — ${e.reason}` : ""}</td>
            </tr>
          ))}
          {entries.length === 0 && (
            <tr><td colSpan={6} className="muted">No operations recorded yet.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}