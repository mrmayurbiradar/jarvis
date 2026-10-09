import { useEffect, useRef, useState } from "react";
import { Approval, AuditEntry, Capabilities, JarvisApi, WorkflowHealth } from "../api";
import { ChatView } from "./ChatView";

interface Props {
  api: JarvisApi;
  pendingCount: number;
  onApprovalChanged: () => void;
}

const QUICK_COMMANDS = [
  "Hello JARVIS",
  "What OS is this?",
  "Run echo hi",
  "List workflows",
];

function CapabilityRow({ name, ok }: { name: string; ok: boolean }) {
  return (
    <div className="readout-row">
      <span className={`dot ${ok ? "ok" : "off"}`} />
      <span className="mono">{name}</span>
      <span className={`mono ${ok ? "ok" : "no"}`}>{ok ? "ONLINE" : "OFF"}</span>
    </div>
  );
}

export function CommandCenter({ api, pendingCount, onApprovalChanged }: Props) {
  const chatRef = useRef<((text: string) => void) | null>(null);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [activity, setActivity] = useState<AuditEntry[]>([]);
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [wf, setWf] = useState<WorkflowHealth | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  // Live panels: poll approvals + recent tool activity every 4s.
  useEffect(() => {
    let alive = true;
    const refresh = () => {
      api.pendingApprovals().then((r) => alive && setApprovals(r), () => {});
      api.audit(9).then((r) => alive && setActivity(r), () => {});
    };
    refresh();
    const t = setInterval(refresh, 4000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [api]);

  // AI core readout: capabilities + workflow engine health (once).
  useEffect(() => {
    let alive = true;
    api.capabilities().then((c) => alive && setCaps(c), () => {});
    api.workflowHealth().then((h) => alive && setWf(h), () => {}); // 501 if unconfigured → silent
    return () => {
      alive = false;
    };
  }, [api]);

  const respond = (a: Approval, decision: "approve" | "deny") => {
    setBusyId(a.id);
    api
      .respondApproval(a.id, decision)
      .then(() => onApprovalChanged())
      .catch(() => {})
      .finally(() => setBusyId(null));
  };

  const decisionClass = (d: string) => (d === "allow" ? "ok" : "no");
  const shortTarget = (t: string): string => {
    if (t.length <= 46) return t;
    return `${t.slice(0, 43)}…`;
  };

  return (
    <div className="command">
      {/* TASK — the conversation with JARVIS */}
      <section className="panel task-panel">
        <header className="panel-head">
          <span className="panel-title">TASK / CONVERSATION</span>
          <span className="panel-sub mono">agent online · C2</span>
        </header>
        <div className="quick-commands">
          {QUICK_COMMANDS.map((c) => (
            <button key={c} className="quick" onClick={() => chatRef.current?.(c)}>
              {c}
            </button>
          ))}
        </div>
        <ChatView api={api} sendExternalRef={chatRef} />
      </section>

      {/* RIGHT RAIL — approvals, tool activity, AI core */}
      <div className="rail">
        <section className="panel rail-panel">
          <header className="panel-head">
            <span className="panel-title">APPROVALS</span>
            {pendingCount > 0 && <span className="badge glow">{pendingCount}</span>}
          </header>
          {approvals.length === 0 ? (
            <p className="muted panel-empty">Queue clear — no actions awaiting your OK.</p>
          ) : (
            approvals.map((a) => (
              <div className="approval-row" key={a.id}>
                <div className="mono approval-cap">{a.capability}</div>
                <div className="mono approval-args">{shortTarget(JSON.stringify(a.target))}</div>
                <div className="approval-actions">
                  <button className="btn-approve" disabled={busyId === a.id} onClick={() => respond(a, "approve")}>
                    Approve
                  </button>
                  <button className="btn-deny" disabled={busyId === a.id} onClick={() => respond(a, "deny")}>
                    Deny
                  </button>
                </div>
              </div>
            ))
          )}
        </section>

        <section className="panel rail-panel">
          <header className="panel-head">
            <span className="panel-title">TOOL ACTIVITY</span>
            <span className="panel-sub mono">live · audit C5</span>
          </header>
          {activity.length === 0 ? (
            <p className="muted panel-empty">No operations recorded yet.</p>
          ) : (
            activity.map((e, i) => (
              <div className="activity-row" key={i}>
                <span className={`mono activity-cap ${decisionClass(e.decision)}`}>{e.capability}</span>
                <span className={`mono ${decisionClass(e.decision)}`}>{e.outcome}</span>
                <span className="mono muted activity-ts">{e.ts.slice(11, 19)}</span>
              </div>
            ))
          )}
        </section>

        <section className="panel rail-panel">
          <header className="panel-head">
            <span className="panel-title">AI CORE</span>
            <span className={`dot ${caps ? "ok" : "off"}`} />
          </header>
          {caps ? (
            <>
              <div className="readout-row">
                <span className="mono muted">platform</span>
                <span className="mono">{caps.platform}</span>
              </div>
              <div className="readout-row">
                <span className="mono muted">deployment</span>
                <span className="mono">{caps.deployment_mode}</span>
              </div>
              {caps.capabilities.shell !== undefined && (
                <CapabilityRow name="shell.run" ok={caps.capabilities.shell} />
              )}
              {caps.capabilities.system_info !== undefined && (
                <CapabilityRow name="system.info" ok={caps.capabilities.system_info} />
              )}
              {caps.capabilities.launch_application !== undefined && (
                <CapabilityRow name="app.launch" ok={caps.capabilities.launch_application} />
              )}
              {caps.mcp && (
                <div className="readout-row">
                  <span className="mono muted">mcp tools</span>
                  <span className="mono ok">{caps.mcp.available ? caps.mcp.tools.join(" · ") : "none"}</span>
                </div>
              )}
              {wf && wf.engine && (
                <div className="readout-row">
                  <span className="mono muted">workflow</span>
                  <span className="mono ok">
                    {wf.engine}
                    {typeof wf.enabled === "number" ? ` · ${wf.enabled} jobs` : ""}
                  </span>
                </div>
              )}
            </>
          ) : (
            <p className="muted panel-empty">Connecting to core…</p>
          )}
        </section>
      </div>
    </div>
  );
}