import { useEffect, useState } from "react";
import { Capabilities, JarvisApi } from "../api";

interface Props {
  api: JarvisApi;
}

export function CapabilitiesView({ api }: Props) {
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .capabilities()
      .then(setCaps)
      .catch((e) => setError(String(e)));
  }, [api]);

  return (
    <div className="panel">
      <h2>Backend capabilities</h2>
      {error && <div className="error">{error}</div>}
      {caps && (
        <table>
          <tbody>
            <tr><th>Platform</th><td>{caps.platform}</td></tr>
            <tr><th>Deployment mode</th><td>{caps.deployment_mode}</td></tr>
            {Object.entries(caps.capabilities).map(([k, v]) => (
              <tr key={k}>
                <th>{k}</th>
                <td className={v ? "ok" : "no"}>{v ? "available" : "unavailable"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}