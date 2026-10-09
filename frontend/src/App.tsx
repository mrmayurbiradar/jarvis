import { useEffect, useState } from "react";
import { JarvisApi } from "./api";
import { clearToken, loadToken, saveToken } from "./token-store";
import { PairingView } from "./components/PairingView";
import { ChatView } from "./components/ChatView";
import { CapabilitiesView } from "./components/CapabilitiesView";
import { AuditView } from "./components/AuditView";
import { NativeView } from "./components/NativeView";
import { ApprovalsView } from "./components/ApprovalsView";
import { CommandCenter } from "./components/CommandCenter";

export default function App() {
  const [api] = useState(() => new JarvisApi());
  const [token, setToken] = useState<string>(() => loadToken());
  const [tab, setTab] = useState<"command" | "chat" | "approvals" | "capabilities" | "audit" | "native">(
    "command",
  );
  const [pendingCount, setPendingCount] = useState(0);

  useEffect(() => {
    api.setToken(token);
  }, [api, token]);

  // Poll the gate-3 queue so the Approvals badge stays live even when the
  // tab is closed — scheduled jobs and chat both queue here.
  useEffect(() => {
    if (!token) return;
    let alive = true;
    const poll = () =>
      api.pendingApprovals().then(
        (rows) => {
          if (alive) setPendingCount(rows.length);
        },
        () => undefined, // offline/unpaired → badge just stays quiet
      );
    poll();
    const t = setInterval(poll, 5000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [api, token]);

  const handlePaired = (tok: string) => {
    saveToken(tok);
    setToken(tok);
  };

  const handleLogout = () => {
    clearToken();
    setToken("");
  };

  if (!token) {
    return <PairingView api={api} onPaired={handlePaired} />;
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <span className="brand-dot" />
          <h1>JARVIS</h1>
          <span className="brand-sub mono">command center</span>
        </div>
        <nav className="tabs">
          <button className={tab === "command" ? "active" : ""} onClick={() => setTab("command")}>Command Center</button>
          <button className={tab === "chat" ? "active" : ""} onClick={() => setTab("chat")}>Chat</button>
          <button className={tab === "approvals" ? "active" : ""} onClick={() => setTab("approvals")}>
            Approvals
            {pendingCount > 0 && <span className="badge glow">{pendingCount}</span>}
          </button>
          <button className={tab === "capabilities" ? "active" : ""} onClick={() => setTab("capabilities")}>Capabilities</button>
          <button className={tab === "audit" ? "active" : ""} onClick={() => setTab("audit")}>Audit log</button>
          <button className={tab === "native" ? "active" : ""} onClick={() => setTab("native")}>This computer</button>
        </nav>
        <button className="logout" onClick={handleLogout}>Unpair</button>
      </header>

      <main>
        {tab === "command" && (
          <CommandCenter
            api={api}
            pendingCount={pendingCount}
            onApprovalChanged={() => api.pendingApprovals().then((r) => setPendingCount(r.length))}
          />
        )}
        {tab === "chat" && <ChatView api={api} />}
        {tab === "approvals" && <ApprovalsView api={api} onChanged={() => api.pendingApprovals().then((r) => setPendingCount(r.length))} />}
        {tab === "capabilities" && <CapabilitiesView api={api} />}
        {tab === "audit" && <AuditView api={api} />}
        {tab === "native" && <NativeView />}
      </main>
    </div>
  );
}