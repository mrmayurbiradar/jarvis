import { useEffect, useState } from "react";
import { inTauri, probeNativeCapabilities, type NativeCapabilities } from "../native";

/**
 * "This computer" panel — shows which client-shell capabilities are actually
 * present. In a browser most are unsupported; the shell degrades gracefully
 * (matrix A1–A11).
 */
export function NativeView() {
  const [caps, setCaps] = useState<NativeCapabilities | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!inTauri()) {
      setCaps({
        notifications: false,
        clipboard: false,
        autostart: false,
        wake_word: false,
        global_hotkey: false,
      });
      return;
    }
    probeNativeCapabilities().then(setCaps).catch((e) => setError(String(e)));
  }, []);

  const rows: [string, boolean][] = caps
    ? [
        ["Notifications", caps.notifications],
        ["Clipboard (permitted)", caps.clipboard],
        ["Startup integration", caps.autostart],
        ["Wake word", caps.wake_word],
        ["Global hotkey", caps.global_hotkey],
      ]
    : [];

  return (
    <div className="panel">
      <h2>This computer</h2>
      <p className="muted">
        {inTauri()
          ? "Running inside the desktop shell — native capabilities below."
          : "Running in a browser — no local machine access (deployment mode C). Native capabilities are unavailable here."}
      </p>
      {error && <div className="error">{error}</div>}
      <table>
        <tbody>
          {rows.map(([name, ok]) => (
            <tr key={name}>
              <th>{name}</th>
              <td className={ok ? "ok" : "no"}>{ok ? "available" : "unavailable"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}