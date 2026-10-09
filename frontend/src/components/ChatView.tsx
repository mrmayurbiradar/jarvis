import { FormEvent, MutableRefObject, useEffect, useRef, useState } from "react";
import { ApiError, JarvisApi } from "../api";
import {
  createRecognizer,
  recognitionSupported,
  speak,
  speechSupported,
  stopSpeaking,
  stripMockPrefix,
  wakeMatch,
} from "../voice";

interface Props {
  api: JarvisApi;
  /** Parent (Command Center) quick-command hook: set to send programmatically. */
  sendExternalRef?: MutableRefObject<((text: string) => void) | null>;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  tool_calls?: number;
}

type Listening = "off" | "mic" | "wake" | "awaiting";

export function ChatView({ api, sendExternalRef }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionId] = useState<string>(() =>
    typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : String(Date.now()),
  );
  // Voice layer
  const micSupported = recognitionSupported();
  const [voiceOn, setVoiceOn] = useState(true); // JARVIS speaks replies
  const [wakeOn, setWakeOn] = useState(false); // "Hey Jarvis" wake word
  const [listening, setListening] = useState<Listening>("off");
  const [interim, setInterim] = useState("");
  const [voiceNote, setVoiceNote] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const recognizerRef = useRef<ReturnType<typeof createRecognizer> | null>(null);
  const busyRef = useRef(false);
  const wakeRef = useRef(wakeOn);
  const voiceRef = useRef(voiceOn);
  const awaitingCommandRef = useRef(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    wakeRef.current = wakeOn;
    voiceRef.current = voiceOn;
  }, [wakeOn, voiceOn]);

  useEffect(() => {
    return () => stopRecognizer();
  }, []);

  // Expose a programmatic send to the Command Center quick commands.
  useEffect(() => {
    if (sendExternalRef) {
      sendExternalRef.current = (text: string) => {
        setInput("");
        sendText(text);
      };
    }
  }, [sendExternalRef]);

  const stopRecognizer = () => {
    recognizerRef.current?.stop();
    recognizerRef.current = null;
    setInterim("");
    setListening("off");
  };

  const startRecognizer = (mode: "mic" | "wake") => {
    stopSpeaking();
    recognizerRef.current = createRecognizer(
      {
        onFinal: (text) => handleVoiceText(text),
        onInterim: (text) => setInterim(text),
        onEnd: () => {
          recognizerRef.current = null;
          if (wakeRef.current && awaitingCommandRef.current) {
            // kept listening for the command after "Hey Jarvis"
            setListening("awaiting");
          } else {
            setListening("off");
          }
          setInterim("");
        },
      },
      mode === "wake", // continuous for wake mode
    );
    recognizerRef.current.start();
    setListening(mode);
    setVoiceNote(null);
  };

  const toggleMic = () => {
    if (listening === "mic") {
      stopRecognizer();
    } else {
      setWakeOn(false);
      startRecognizer("mic");
    }
  };

  const toggleWake = () => {
    if (wakeOn) {
      stopRecognizer();
      setWakeOn(false);
      return;
    }
    setWakeOn(true);
    startRecognizer("wake");
  };

  const handleVoiceText = (text: string) => {
    if (wakeRef.current) {
      const { awake, command } = wakeMatch(text);
      if (awake) {
        if (voiceRef.current) speak("Yes, sir?");
        if (command) {
          awaitingCommandRef.current = false;
          sendText(command);
        } else {
          awaitingCommandRef.current = true; // wait for the next phrase as the command
          setListening("awaiting");
        }
      } else if (awaitingCommandRef.current && text.trim()) {
        awaitingCommandRef.current = false;
        sendText(text);
      }
      return;
    }
    // push-to-talk: the transcript is the command
    if (text.trim()) sendText(text);
  };

  const sendText = async (text: string) => {
    const clean = text.trim();
    if (!clean || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    setMessages((m) => [...m, { role: "user", content: clean }]);
    try {
      const r = await api.chat(clean, sessionId);
      setMessages((m) => [
        ...m,
        { role: "assistant", content: r.text, tool_calls: r.tool_calls },
      ]);
      if (voiceRef.current && speechSupported()) {
        speak(stripMockPrefix(r.text));
      }
    } catch (err) {
      const detail = err instanceof ApiError ? String(err.detail) : String(err);
      setError(detail);
      setMessages((m) => [...m, { role: "assistant", content: `⚠ ${detail}` }]);
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;
    setInput("");
    sendText(text);
  };

  const listeningLabel =
    listening === "mic"
      ? "Listening… click to stop"
      : listening === "wake"
        ? "Wake word on — say “Hey Jarvis”"
        : listening === "awaiting"
          ? "Go ahead, sir…"
          : "";

  return (
    <div className="chat">
      <div className="messages">
        {messages.length === 0 && (
          <p className="muted">
            Say something — e.g. "hello", "run echo hi", "what OS is this?". If you have a
            mic, click <span className="chip-inline">🎤</span> and talk to JARVIS.
          </p>
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

      <div className="voice-bar">
        <div className="voice-controls">
          <button
            className={`mic-btn ${listening === "mic" ? "active" : ""}`}
            disabled={!micSupported || wakeOn || busy}
            onClick={toggleMic}
            title={micSupported ? "Push-to-talk: click, speak, done" : "Speech recognition unsupported in this browser"}
          >
            🎤
          </button>
          <button
            className={`wake-btn ${wakeOn ? "active" : ""}`}
            disabled={!micSupported}
            onClick={toggleWake}
            title='Continuously listen for "Hey Jarvis" (experimental)'
          >
            Hey Jarvis
          </button>
          <label className="voice-toggle" title="JARVIS speaks replies aloud">
            <input
              type="checkbox"
              checked={voiceOn}
              onChange={(e) => setVoiceOn(e.target.checked)}
            />
            <span>Speaks</span>
          </label>
        </div>
        {(listening !== "off" || interim) && (
          <div className={`voice-status ${listening === "awaiting" ? "ok" : ""}`}>
            {listeningLabel}
            {interim && <span className="interim">“{interim}”</span>}
          </div>
        )}
        {voiceNote && <div className="muted">{voiceNote}</div>}
        {!micSupported && (
          <div className="muted">
            🎤 Unsupported here — use Chrome/Edge, and open the app via{" "}
            <span className="mono">http://localhost:1420</span> (browsers only allow the
            mic on localhost or https).
          </div>
        )}
      </div>

      <form className="composer" onSubmit={handleSubmit}>
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