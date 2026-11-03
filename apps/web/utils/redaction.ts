// Phase 1F: Secret Guard — client-side mirror of apps/api/security/redaction.py.
//
// The backend is the enforcement point: nothing reaches any store, log or
// model call without passing through the server redactor. This module only
// keeps the optimistic UI honest — the bubble you see after pressing Send
// is exactly what the server persists, so a raw credential never lingers
// in the rendered DOM. Keep the patterns in sync with the Python source.

export interface ClientRedaction {
  text: string;
  kinds: string[];
}

// Keyword=value — "is" allowed for password-shaped words only, matching
// the server ("my secret is out" stays untouched). The capture group is
// the secret VALUE (mirrors the Python ([^\s'\",;:]+) group).
const KEYWORD =
  /(?:(?:password|passwd|passphrase|pwd)(?:\s+is|\s*[:=])|(?:secret|api[\s_-]*key|access[\s_-]*token)\s*[:=])\s*([^\s'",;:]+)/gi;
const BEARER = /\bBearer\s+[A-Za-z0-9\-._~+/]{8,}=*/gi;
const GOOGLE_KEY = /\bAIza[0-9A-Za-z\-_]{35}\b/g;
const PREFIXED_KEY = /\bsk-(?:live-|test-|proj-)?[A-Za-z0-9_\-]{16,}/g;
const PEM =
  /-----BEGIN\s+(?:RSA|EC|DSA|OPENSSH|PGP|ENCRYPTED)?\s*PRIVATE\s+KEY(?:\s+BLOCK)?-----[\s\S]*?(?:-----END\s+(?:RSA|EC|DSA|OPENSSH|PGP|ENCRYPTED)?\s*PRIVATE\s+KEY(?:\s+BLOCK)?-----|$)|MII[A-Za-z0-9/+]{40,}/g;
const HEX = /\b[0-9a-fA-F]{32,}\b/g;
const B64 = /\b[A-Za-z0-9+/]{40,}={0,2}(?![A-Za-z0-9+/=])/g;
const CARD = /\b(?:\d[ -]?){12,18}\d\b/g;

function luhnValid(digits: string): boolean {
  let total = 0;
  for (let index = 0; index < digits.length; index += 1) {
    let value = Number(digits[digits.length - 1 - index]);
    if (index % 2 === 1) {
      value *= 2;
      if (value > 9) value -= 9;
    }
    total += value;
  }
  return total % 10 === 0;
}

/** Replace every credential-shaped value with a [REDACTED: kind] marker.
 * Benign mentions ("explain password reset flow") pass through as-is. */
export function redactSecrets(input: string): ClientRedaction {
  const kinds = new Set<string>();
  let text = input;

  const replace = (
    pattern: RegExp,
    kind: string,
    valueOf?: (groups: (string | undefined)[]) => string | undefined,
  ) => {
    text = text.replace(
      pattern,
      (match: string, ...args: (string | number | Record<string, string> | undefined)[]) => {
        const groups = args.slice(0, -1) as (string | undefined)[];
        // Keyword pattern captures only the VALUE — keep the benign keyword.
        if (valueOf && groups.length > 0) {
          const value = valueOf(groups);
          if (value === undefined) return match;
          kinds.add(kind);
          return `${match.slice(0, match.length - value.length)}[REDACTED: ${kind}]`;
        }
        kinds.add(kind);
        return `[REDACTED: ${kind}]`;
      },
    );
  };

  replace(PEM, "private key");
  replace(GOOGLE_KEY, "API key");
  replace(PREFIXED_KEY, "API key");
  replace(BEARER, "bearer token");
  replace(KEYWORD, "password", (groups) => groups[0]);
  replace(HEX, "secret");
  // Base64 blobs that look like ordinary compressed prose stay untouched,
  // same heuristic as the server (no lowercase run longer than five).
  text = text.replace(B64, (match) =>
    /[a-z]{6}/.test(match) ? match : (kinds.add("secret"), "[REDACTED: secret]"),
  );
  text = text.replace(CARD, (match) => {
    const digits = match.replace(/[ -]/g, "");
    if (digits.length < 13 || digits.length > 19 || !luhnValid(digits)) return match;
    kinds.add("card number");
    return "[REDACTED: card number]";
  });

  return { text, kinds: [...kinds] };
}
