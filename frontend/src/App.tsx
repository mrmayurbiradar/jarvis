import { useEffect, useState } from "react";
import { JarvisApi } from "./api";
import { clearToken, loadToken, saveToken } from "./token-store";
import { PairingView } from "./components/PairingView";
import { ChatView } from "./components/ChatView";
import { CapabilitiesView } from "./components/CapabilitiesView";
import { AuditView } from "./components/AuditView";
import { NativeView } from "./components/NativeView";

export default function App() {
  const [api] = useState(() => new JarvisApi());
  const [token, setToken] = useState<string>(() => loadToken());
  const [tab, setTab] = useState<"chat" | "capabilities" | "audit" | "native">("chat");

  useEffect(() => {
    api.setToken(token);
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
        <h1>JARVIS</h1>
        <nav className="tabs">
          <button className={tab === "chat" ? "active" : ""} onClick={() => setTab("chat")}>Chat</button>
          <button className={tab === "capabilities" ? "active" : ""} onClick={() => setTab("capabilities")}>Capabilities</button>
          <button className={tab === "audit" ? "active" : ""} onClick={() => setTab("audit")}>Audit log</button>
          <button className={tab === "native" ? "active" : ""} onClick={() => setTab("native")}>This computer</button>
        </nav>
        <button className="logout" onClick={handleLogout}>Unpair</button>
      </header>

      <main>
        {tab === "chat" && <ChatView api={api} />}
        {tab === "capabilities" && <CapabilitiesView api={api} />}
        {tab === "audit" && <AuditView api={api} />}
        {tab === "native" && <NativeView />}
      </main>
    </div>
  );
}