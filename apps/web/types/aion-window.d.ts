/// <reference types="./next-env" />

// Augment the DOM Window interface for AION's SSE store.
interface Window {
  __aionSse?: EventSource;
}
