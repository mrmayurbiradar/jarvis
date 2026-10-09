/**
 * Browser voice layer for JARVIS (client-side STT/TTS, zero dependencies).
 *
 * Uses the Web Speech API: SpeechRecognition for input (speech → text) and
 * speechSynthesis for output (text → speech). No backend changes, no keys.
 *
 * Caveats:
 * - SpeechRecognition is Chromium-only in practice (Chrome/Edge/Opera); the
 *   mic also requires a *secure context* — open the app via `http://localhost`
 *   or an https URL, not a bare LAN IP.
 * - speechSynthesis works in every modern browser and does not need a secure
 *   context, so spoken replies fall back gracefully.
 *
 * The backend provider layer (C7: LLM/STT/TTS abstraction, e.g. Whisper +
 * wake-word engines like Porcupine) is the P2 route; this gives the feel now.
 */

export interface RecognizerEvents {
  onFinal: (text: string) => void;
  onInterim: (text: string) => void;
  onEnd: () => void;
}

export interface Recognizer {
  start(): void;
  stop(): void;
}

export function recognitionSupported(): boolean {
  if (typeof window === "undefined") return false;
  const w = window as unknown as Record<string, unknown>;
  return Boolean(w.SpeechRecognition || w.webkitSpeechRecognition);
}

export function speechSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

/**
 * Wrap SpeechRecognition with a stable shape. `continuous` keeps listening
 * after a result (wake-word mode); otherwise it auto-stops after silence.
 */
export function createRecognizer(events: RecognizerEvents, continuous = false): Recognizer {
  const w = window as unknown as {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  };
  const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition;
  if (!Ctor) throw new Error("SpeechRecognition is not supported in this browser");
  const rec = new Ctor();
  rec.continuous = continuous;
  rec.interimResults = true;
  rec.lang = "en-US";
  rec.onresult = (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i];
      const transcript = result[0]?.transcript ?? "";
      if (result.isFinal) {
        events.onFinal(transcript);
      } else {
        interim += transcript;
      }
    }
    events.onInterim(interim);
  };
  rec.onerror = () => {
    // Network/no-speech/not-allowed etc. — end quietly so the UI resets.
    events.onEnd();
  };
  rec.onend = () => events.onEnd();
  return {
    start: () => rec.start(),
    stop: () => {
      try {
        rec.stop();
      } catch {
        /* already stopped */
      }
    },
  };
}

interface SpeechRecognitionLike {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechResultEvent) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}

interface SpeechResultEvent {
  resultIndex: number;
  results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }>;
}

/** Strip the mock LLM's "(mock) " prefix so the voice reply reads naturally. */
export function stripMockPrefix(text: string): string {
  return text.replace(/^\(mock\)\s*/i, "");
}

export interface WakeResult {
  awake: boolean;
  /** Text after the wake phrase — the actual command, if any. */
  command: string;
}

/**
 * Match a wake phrase at the start of an utterance: "hey jarvis",
 * "jarvis", optionally with punctuation before the command.
 * Anything after the phrase is the command.
 */
export function wakeMatch(transcript: string): WakeResult {
  const match = transcript.trim().match(/^(?:hey\s+)?jarvis[\s,.:!-]*([\s\S]*)$/i);
  if (!match) return { awake: false, command: "" };
  return { awake: true, command: match[1].trim() };
}

/** Prefer a calm, mid-pitch English voice — closer to the JARVIS tone. */
export function pickEnglishVoice(
  voices: SpeechSynthesisVoice[],
): SpeechSynthesisVoice | null {
  if (!voices.length) return null;
  const english = voices.filter((v) => v.lang.toLowerCase().startsWith("en"));
  const pool = english.length ? english : voices;
  const preferred = ["Google US English", "Samantha", "Daniel", "Microsoft David", "Microsoft Aria"];
  for (const name of preferred) {
    const hit = pool.find((v) => v.name.includes(name));
    if (hit) return hit;
  }
  return pool[0];
}

/** Speak text aloud; cancels anything currently speaking. No-op if unsupported. */
export function speak(text: string, pitch = 0.85): void {
  if (!speechSupported()) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  const voice = pickEnglishVoice(window.speechSynthesis.getVoices());
  if (voice) utterance.voice = voice;
  utterance.rate = 1.0;
  utterance.pitch = pitch; // slightly deeper than the default — more assistant-like
  window.speechSynthesis.speak(utterance);
}

export function stopSpeaking(): void {
  if (speechSupported()) window.speechSynthesis.cancel();
}