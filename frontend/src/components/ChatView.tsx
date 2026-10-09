import { FormEvent, MutableRefObject, useEffect, useRef, useState } from "react";
import { ApiError, JarvisApi } from "../api";
import { inTauri } from "../native";
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

function microphonePermissionHelp(): string {
  return inTauri()
    ? "Microphone access is blocked for JARVIS. Allow it in your operating system's privacy settings, then restart the app."
    : "Microphone access is blocked. Allow it for this site in your browser settings, then enable wake listening again.";
}

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
    const current = recognizerRef.current;
    recognizerRef.current = null;
    current?.stop();
    setInterim("");
    setListening("off");
  };

  const startRecognizer = (mode: "mic" | "wake") => {
    stopSpeaking();
    let activeRecognizer: ReturnType<typeof createRecognizer> | null = null;
    try {
      activeRecognizer = createRecognizer(
        {
          onFinal: (text) => handleVoiceText(text),
          onInterim: (text) => setInterim(text),
          onError: (code) => {
            if (code === "not-allowed" || code === "service-not-allowed" || code === "audio-capture") {
              wakeRef.current = false;
              setWakeOn(false);
              setVoiceNote(
                code === "audio-capture"
                  ? "No microphone was found. Connect one and enable wake listening again."
                  : microphonePermissionHelp(),
              );
            }
          },
          onEnd: () => {
            if (recognizerRef.current !== activeRecognizer) return;
            recognizerRef.current = null;
            setInterim("");
            if (wakeRef.current && mode === "wake") {
              setListening(awaitingCommandRef.current ? "awaiting" : "wake");
              window.setTimeout(() => {
                if (wakeRef.current && recognizerRef.current === null) startRecognizer("wake");
              }, 350);
            } else {
              setListening("off");
            }
          },
        },
        mode === "wake",
      );
      recognizerRef.current = activeRecognizer;
      activeRecognizer.start();
      setListening(mode === "wake" && awaitingCommandRef.current ? "awaiting" : mode);
      setVoiceNote(null);
    } catch {
      recognizerRef.current = null;
      if (mode === "wake") {
        wakeRef.current = false;
        setWakeOn(false);
      }
      setListening("off");
      setVoiceNote(`Could not start the microphone. ${microphonePermissionHelp()}`);
    }
  };

  const toggleMic = () => {
    if (listening === "mic") {
      stopRecognizer();
    } else {
      wakeRef.current = false;
      setWakeOn(false);
      startRecognizer("mic");
    }
  };

  const toggleWake = () => {
    if (wakeRef.current) {
      wakeRef.current = false;
      stopRecognizer();
      setWakeOn(false);
      awaitingCommandRef.current = false;
      return;
    }
    wakeRef.current = true;
    awaitingCommandRef.current = false;
    setWakeOn(true);
    startRecognizer("wake");
  };

  const handleVoiceText = (text: string) => {
    if (wakeRef.current) {
      const { awake, command } = wakeMatch(text);
      if (awake) {
        if (command) {
          awaitingCommandRef.current = false;
          sendText(command);
        } else {
          awaitingCommandRef.current = true;
          stopRecognizer();
          setListening("awaiting");
          const resumeWake = () => {
            if (wakeRef.current) startRecognizer("wake");
          };
          if (voiceRef.current && speechSupported()) speak("Yes, sir?", 0.85, resumeWake);
          else resumeWake();
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
    const resumeWake = wakeRef.current;
    if (resumeWake) stopRecognizer();
    busyRef.current = true;
    setBusy(true);
    setError(null);
    setMessages((m) => [...m, { role: "user", content: clean }]);
    let wakeResumesAfterSpeech = false;
    try {
      const r = await api.chat(clean, sessionId);
      setMessages((m) => [
        ...m,
        { role: "assistant", content: r.text, tool_calls: r.tool_calls },
      ]);
      if (voiceRef.current && speechSupported()) {
        wakeResumesAfterSpeech = resumeWake;
        speak(stripMockPrefix(r.text), 0.85, () => {
          if (wakeRef.current) startRecognizer("wake");
        });
      }
    } catch (err) {
      const detail = err instanceof ApiError ? String(err.detail) : String(err);
      setError(detail);
      setMessages((m) => [...m, { role: "assistant", content: `⚠ ${detail}` }]);
    } finally {
      busyRef.current = false;
      setBusy(false);
      if (resumeWake && !wakeResumesAfterSpeech && wakeRef.current) startRecognizer("wake");
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
        ? "Listening for “Hey Jarvis”…"
        : listening === "awaiting"
          ? "Listening for your command…"
          : "";

  return (
    <div className="chat">
      <div className="messages">
        {messages.length === 0 && (
          <p className="muted">
            Enable <span className="chip-inline">Hey Jarvis</span> once to arm wake listening, then say
            “Hey Jarvis” followed by your request. Or use the mic for push-to-talk.
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
            type="button"
            aria-pressed={wakeOn}
            aria-label={wakeOn ? "Disable Hey Jarvis wake listening" : "Enable Hey Jarvis wake listening"}
            onClick={toggleWake}
            title='Click once to allow the microphone, then say "Hey Jarvis" to activate JARVIS'
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