# Phase 7 — Social via official APIs (design + safe scaffolding, dry-run only)

## Scope decision (honest boundaries)

This phase ships **scaffolding, not posting**. Real posting is explicitly out
of this session: it needs owner-provided credentials and, for TikTok, an
approved app review. Everything below runs in **dry-run mode by default** —
the code path builds and validates the exact official-API request and returns
a preview, but performs **zero network calls** unless three independent gates
all say yes:

1. `config.yaml → social.live_enabled: true` (this machine's config decides,
   never the request — same policy as browser headlessness and voice backends),
2. a real OAuth token file exists in `~/.aion/` written by the owner, and
3. the tool call itself already passed the human approval gate (ledger +
   one-time bridge grant) like every other protected action.

No passwords. No scraping. No unofficial endpoints. Only the documented
Graph API / Pinterest API / TikTok Content Posting API surfaces.

## Files

| File | Change |
|---|---|
| `desktop/aion_desktop/social/__init__.py` | new package |
| `desktop/aion_desktop/social/oauth.py` | PKCE (S256) + state helpers, `TokenVault` for `~/.aion` with 0600 |
| `desktop/aion_desktop/social/providers.py` | `SocialProvider` interface + Meta Graph (FB/IG), Pinterest, TikTok specs; request builders + dry-run executor |
| `desktop/aion_desktop/bridge.py` | `social_post` executor in `_executor_for`; `social` config read in `build_app` (config, never request) |
| `desktop/config.yaml` + `.env.example` | `social:` block (live_enabled: false, per-provider client ids from env) |
| `apps/api/config.py` | add `social_post` to default `AION_PROTECTED_DESKTOP_TOOLS` |
| `apps/api/.env.example` | same |
| `apps/api/services/chat_approval.py` | `social_post` param whitelist (`platform`, `content`) + imperative-clause heuristic ("post \"…\" to pinterest") |
| `desktop/tests/test_social.py` | PKCE vector, vault permissions, dry-run shapes, param spoofing |
| `apps/api/tests/test_chat_approvals.py` | social intent detection + validation + injection tests |
| `docs/PR_NOTES.md`, `docs/AION_MVP_PLAN.md` | honest status + owner credential checklist |

## Security model (unchanged, extended)

- `social_post` joins the **protected set**, so: chat can only *create
  pending approvals* for it (Phase 2 rules), the scheduler can only queue it
  (Phase 5 rules), and execution still requires approve → grant → bridge.
- **Config decides live mode.** Request parameters `live`, `dry_run`,
  `token`, `client_secret` are dropped by `validate_parameters` (forbidden-key
  regex already covers `token`/`secret`) and ignored by the executor. A test
  proves a spoofed `"live": true` changes nothing.
- **Tokens never leave the vault.** `TokenVault` writes `<provider>.json`
  with `O_CREAT | 0o600`, refuses to read files that are symlinks or
  world/group-readable, and the dry-run payload contains no auth material.
  Audit/ledger stores only `platform` + hashed content (existing redaction).
- OAuth2 scaffold: `state` (token_urlsafe) + PKCE S256 per RFC 7636; the
  exchange function exists but performs network I/O only under the triple
  gate above. Client secrets are read from env vars
  (`AION_SOCIAL_META_CLIENT_SECRET` etc.), never from config.yaml, never
  logged (repr-safe dataclass).
- Gemini function declarations remain exactly
  `calculator, text_analysis, current_datetime` — the existing tests prove
  it; this phase adds nothing to the model's tool surface.

## Dry-run contract (what the owner sees after approving)

```json
{
  "success": true,
  "mode": "dry_run",
  "platform": "pinterest",
  "request_preview": {
    "method": "POST",
    "url": "https://api.pinterest.com/v5/boards/{board}/pins",
    "payload_keys": ["note", "title"],
    "content_preview": "first 120 chars…"
  },
  "next_steps": "Create a Pinterest developer app, … (see docs/PR_NOTES.md)"
}
```

Unknown platform → `success: false` with the supported list. Instagram text
without media and TikTok without video are refused at validation (official
API requirements), with the reason surfaced.

## E2E plan (live, with bridge + backend running)

1. Chat: `Post "Hello from AION" to pinterest` → pending approval (queue).
2. Spoof attempt in the same message (`live true`, grant-token wording) →
   still only a pending row; params show `{platform, content}` only.
3. Approve via REST → bridge executes → result is `mode: dry_run`, the
   vault directory is never touched, audit chain complete, logs contain no
   token/secret material (grep count 0).
4. Reject path leaves everything inert.

## Risks / owner actions (documented, not guessed)

- Meta: Graph API app + FB Page access token; IG requires Business/Creator
  account and a published app (`instagram_content_publish` permission review).
- Pinterest: developer app, `board_access` scope, approved partner access
  for pin creation.
- TikTok: Content Posting API needs **app review**; unreviewed apps can only
  post private/draft via `DIRECT_POST` fallback — flagged in provider notes.
- Credentials + a real redirect URI (localhost for dev) must come from the
  owner before any live code path can be exercised; until then everything
  is dry-run by construction, which is exactly what this phase tests.
