import { FormEvent, useEffect, useRef, useState } from "react";
import { ApiError, JarvisApi } from "../api";

interface Props {
  api: JarvisApi;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  tool_calls?: number;
}

export function ChatView({ api }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionId] = useState<string>(() =>
    typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : String(Date.now()),
  );
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async (e: FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setMessages((m) => [...m, { role: "user", content: text }]);
    setInput("");
    setBusy(true);
    setError(null);
    try {
      const r = await api.chat(text, sessionId);
      setMessages((m) => [
        ...m,
        { role: "assistant", content: r.text, tool_calls: r.tool_calls },
      ]);
    } catch (err) {
      const detail = err instanceof ApiError ? String(err.detail) : String(err);
      setError(detail);
      setMessages((m) => [...m, { role: "assistant", content: `⚠ ${detail}` }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="chat">
      <div className="messages">
        {messages.length === 0 && (
          <p className="muted">Say something — e.g. "hello", "run echo hi", "what OS is this?".</p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="bubble">
              {m.content}
              {m.role === "assistant" && m.tool_calls ? (
                <span className="tool-count">· {m.tool_calls} tool call{m.tool_calls > 1 ? "s" : ""}</span>
              ) : null}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <form className="composer" onSubmit={send}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Message JARVIS…"
          disabled={busy}
        />
        <button type="submit" disabled={busy || !input.trim()}>Send</button>
      </form>
      {error && <div className="error">{error}</div>}
    </div>
  );
}