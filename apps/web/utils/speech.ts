/**
 * Minimal typed wrapper around the browser Web Speech API.
 *
 * The API is not in TypeScript's lib.dom, and we add no dependencies for
 * it. Recognition runs entirely in the browser (Chromium/Safari): the
 * transcript is handed to the chat composer, so dictated text enters the
 * ordinary POST /api/chat path and every chat-path rule applies to it.
 * No audio ever reaches the AION backend.
 */

interface SpeechRecognitionAlternativeLike {
  transcript: string;
  confidence: number;
}

interface SpeechRecognitionResultLike {
  readonly length: number;
  readonly isFinal: boolean;
  item(index: number): SpeechRecognitionAlternativeLike;
  [index: number]: SpeechRecognitionAlternativeLike;
}

interface SpeechRecognitionResultListLike {
  readonly length: number;
  item(index: number): SpeechRecognitionResultLike;
  [index: number]: SpeechRecognitionResultLike;
}

interface SpeechRecognitionEventLike {
  results: SpeechRecognitionResultListLike;
  error?: string | null;
}

interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionEventLike) => void) | null;
  onend: (() => void) | null;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

function getRecognitionCtor(): SpeechRecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as Record<string, unknown>;
  const ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  return typeof ctor === "function" ? (ctor as SpeechRecognitionConstructor) : null;
}

/** False on Firefox et al. — callers hide the mic button instead of breaking. */
export function speechRecognitionSupported(): boolean {
  return getRecognitionCtor() !== null;
}

export interface Dictation {
  stop(): void;
}

/**
 * Start one dictation session. `onFinal` fires with each finalized
 * transcript chunk; `onError` reports a user-facing message. The session
 * stops itself when the user releases the mic or the browser ends it.
 */
export function startDictation(
  onFinal: (text: string) => void,
  onError: (message: string) => void,
  onEnd: () => void,
): Dictation | null {
  const Ctor = getRecognitionCtor();
  if (!Ctor) return null;
  const recognition = new Ctor();
  recognition.lang = navigator.language || "en-US";
  recognition.interimResults = false;
  recognition.continuous = true;
  recognition.maxAlternatives = 1;
  recognition.onresult = (event) => {
    const last = event.results[event.results.length - 1];
    if (last?.isFinal) onFinal(last[0].transcript.trim());
  };
  recognition.onerror = (event) => {
    const code = event.error ?? "unknown";
    onError(
      code === "not-allowed" || code === "service-not-allowed"
        ? "Microphone access was denied. Allow it in browser settings to dictate."
        : `Speech recognition failed: ${code}`,
    );
  };
  recognition.onend = () => onEnd();
  try {
    recognition.start();
  } catch {
    return null;
  }
  return {
    stop() {
      try {
        recognition.stop();
      } catch {
        /* already ended */
      }
    },
  };
}
