import { useState } from "react";
import { ApiError, JarvisApi } from "../api";

interface Props {
  api: JarvisApi;
  onPaired: (token: string) => void;
}

export function PairingView({ api, onPaired }: Props) {
  const [displayName, setDisplayName] = useState("");
  const [code, setCode] = useState<string | null>(null);
  const [confirmCode, setConfirmCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const request = async () => {
    setError(null);
    setBusy(true);
    try {
      const r = await api.requestPairing(displayName.trim() || "my-computer");
      setCode(r.code);
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    setError(null);
    setBusy(true);
    try {
      const r = await api.confirmPairing(confirmCode.trim());
      onPaired(r.token);
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="pairing">
      <h1>JARVIS</h1>
      <p className="muted">
        Pair this computer with the JARVIS backend. A remote server can never control
        this machine without an explicitly paired, authorized worker.
      </p>

      <label>
        Display name
        <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="my-computer" />
      </label>
      <button onClick={request} disabled={busy}>Request pairing code</button>

      {code && (
        <div className="code-box">
          <div className="code">{code}</div>
          <p className="muted">Enter the code to confirm the pairing.</p>
          <input value={confirmCode} onChange={(e) => setConfirmCode(e.target.value)} placeholder="6-digit code" />
          <button onClick={confirm} disabled={busy}>Confirm pairing</button>
        </div>
      )}

      {error && <div className="error">{error}</div>}
    </div>
  );
}