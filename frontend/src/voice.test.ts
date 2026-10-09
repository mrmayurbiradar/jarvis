import { describe, expect, it } from "vitest";
import { pickEnglishVoice, stripMockPrefix, wakeMatch } from "./voice";

describe("stripMockPrefix", () => {
  it("removes the mock prefix for natural speech", () => {
    expect(stripMockPrefix("(mock) hello")).toBe("hello");
    expect(stripMockPrefix("(Mock) system is ready")).toBe("system is ready");
  });

  it("leaves normal replies untouched", () => {
    expect(stripMockPrefix("The audit log is clean, sir.")).toBe(
      "The audit log is clean, sir.",
    );
  });
});

describe("wakeMatch", () => {
  it("wakes on 'hey jarvis' at the start", () => {
    expect(wakeMatch("hey jarvis run the daily report")).toEqual({
      awake: true,
      command: "run the daily report",
    });
  });

  it("wakes on bare 'jarvis'", () => {
    expect(wakeMatch("jarvis, what time is it")).toEqual({
      awake: true,
      command: "what time is it",
    });
  });

  it("wakes with no command — just the phrase", () => {
    expect(wakeMatch("Hey Jarvis.")).toEqual({ awake: true, command: "" });
  });

  it("does not wake on unrelated speech", () => {
    expect(wakeMatch("let me check the weather")).toEqual({
      awake: false,
      command: "",
    });
  });
});

describe("pickEnglishVoice", () => {
  const voices = (lang: string, name: string): SpeechSynthesisVoice =>
    ({ lang, name }) as SpeechSynthesisVoice;

  it("prefers an English voice when available", () => {
    const v = pickEnglishVoice([voices("fr-FR", "Amélie"), voices("en-GB", "Daniel")]);
    expect(v?.name).toBe("Daniel");
  });

  it("falls back to the first voice when no English is present", () => {
    const v = pickEnglishVoice([voices("de-DE", "Katja")]);
    expect(v?.name).toBe("Katja");
  });

  it("returns null for an empty list", () => {
    expect(pickEnglishVoice([])).toBeNull();
  });
});