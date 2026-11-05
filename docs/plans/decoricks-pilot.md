# Decoricks Pilot — AION Workflow Design (plan only)

**Status: DESIGN ONLY.** No credentials, no live API calls, nothing in this
document is built. It maps three real operating routines of Decoricks (a
Shopify home-decor store) onto AION entities as they exist today, and marks
exactly where a real pilot would need new, credential-backed capability.

Reference shapes (current code, not invented):

- `POST /api/workflows` body: `{ name, description, agents }` where
  `agents ⊆ {Planner, Research, Critic, Memory}` (model-safe whitelist —
  anything else is a 400). `POST /api/workflows/{id}/run` body:
  `{ input: string ≤ 4000 chars }`, returning `{ task_id, status, answer,
confidence, processing_time_ms }`.
- Desktop side effects (`file_write`, `file_copy`, `browser_navigate`,
  `social_post`, …) are NOT part of a workflow's agent list — workflows
  only synthesize text. Anything that touches the store's files or platforms
  goes through the approval ledger: create pending → human approves →
  one-time bridge grant → executes exactly once.
- Chat can create those approval requests ("Write '<draft>' to
  ~/decoricks/drafts/…"), which is the intended human-in-the-loop seam.

---

## Workflow 1 — Product Description Drafter

Turns a bare product spec into publish-ready copy. Output is a **draft
file on the host**, never a direct store change.

```json
{
  "name": "Decoricks Product Description Drafter",
  "description": "Research category/SEO context, draft SEO-ready Shopify product copy, critic-verify against the spec, remember tone preferences.",
  "agents": ["Research", "Planner", "Critic", "Memory"]
}
```

Example `run.input` (≤ 4000 chars):

> Product: Jute-woven round storage basket, 40cm, natural undyed.
> Target: "storage baskets" page 1, tone: warm, minimal, no hype words.
> Specs: handwoven jute, 40x40x32cm, 600g, foldable liner. Avoid: claims
> about sustainability certifications we don't have.

Expected output: title (< 70 chars), 2-paragraph description, 5 bullet
specs, meta description (< 160 chars), 3 internal-link suggestions — as
plain text the operator then pastes into Shopify admin by hand.

| Aspect               | Answer                                                                                                                                                                                                  |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Data needed          | Product spec sheet (pasted in `input`, or CSV exported from Shopify admin → `file_read` approval to ingest); brand tone guide (stored in AION Memory via the memory API, or pasted)                     |
| Human-approved       | Writing the draft to disk (`file_write`, e.g. `~/decoricks/drafts/`); anything that reaches Shopify                                                                                                     |
| Credentials required | **None** for the draft itself. Publishing to Shopify = **Shopify Admin API** (custom-app token, `products` scope) — does not exist in AION today; would be a new provider behind the same approval gate |

## Workflow 2 — Meta Ad Copy Variant Studio

Generates variants for one campaign concept so a human picks finalists.

```json
{
  "name": "Decoricks Meta Ad Copy Studio",
  "description": "Research audience angles for a decor promotion, plan 3 tone variants, critic-check against Meta character limits and prohibited claims.",
  "agents": ["Research", "Planner", "Critic"]
}
```

Example `run.input`:

> Campaign: Autumn linen refresh, 20% off throws & cushion covers, ends
> Oct 15. Audiences: (a) homeowners 28-45, (b) interior-design interest,
> (c) past purchasers. Produce 3 primary-text variants (<= 125 chars each,
> hook first), 3 headlines (<= 40 chars), 1 description (<= 30 chars).
> No before/after claims, no price-flash "ending soon" wording on
> audience (a).

Expected output: a labeled matrix of variants with char counts, plus the
critic's compliance notes (what was trimmed and why).

| Aspect               | Answer                                                                                                                                                                                                                                                                                                              |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Data needed          | Campaign brief (pasted), current catalogue/prices (CSV export or `file_read` of the operator's price list), past ad performance screenshots/CSV (optional, better)                                                                                                                                                  |
| Human-approved       | `social_post` is already a protected tool (approval-gated, dry-run by default). Even after credentials, every live post needs a human click; variants are just text until then                                                                                                                                      |
| Credentials required | **Meta Ads API** (system-user token, `ads_management`) for actual campaign object creation — NOT the same as the Page-level `social_post` scaffold in `desktop/aion_desktop/social/`, which posts to a Page feed only. Ad creation is a genuinely new provider; app review + Business Manager assets are owner work |

## Workflow 3 — Weekly SEO & Content Checklist

A recurring Monday-morning routine: a fresh checklist grounded in the
store's actual category pages, saved to disk for the operator to work
through.

```json
{
  "name": "Decoricks Weekly SEO Checklist",
  "description": "Research current gaps for home-decor queries, plan a week-sized checklist (titles, alt text, collection copy, one blog brief), critic-trim to what is actually doable in a week, remember last week's unfinished items.",
  "agents": ["Research", "Planner", "Critic", "Memory"]
}
```

Example `run.input`:

> Store: decoricks.com, categories: baskets, wall decor, cushions,
> lighting. Last week: 3 of 6 done (unfinished: alt-text pass on baskets,
> rug-care blog brief). This week's focus: pre-Diwali traffic. Give me a
> checklist max 6 items, each with the exact page, the action, and a
> done-criterion.

Expected output: 6-item checklist (page → action → done-criterion), with
last week's leftovers merged in, dated heading suitable for a markdown
file.

Scheduling WITHOUT back-fill is exactly the current Phase 5 semantics: a
weekly interval schedule fires only while the API process runs, and at fire
time it can only **create a pending approval** — never execute.

| Aspect               | Answer                                                                                                                                                                                                                    |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Data needed          | Category list + last-week status (pasted into `input`, or read via approved `file_read` of a checklist file the previous week created); public pages via approved `browser_navigate`/screenshot if a live audit is wanted |
| Human-approved       | `file_write` of the weekly checklist file; every `browser_navigate` of a live audit; the schedule itself is CRUD-gated when auth is on                                                                                    |
| Credentials required | **None.** This workflow runs fully inside what AION already does (model-safe agents + approval-gated desktop tools + opt-in scheduler)                                                                                    |

---

## Pilot-readiness order (for a later session, not this one)

1. **Start with Workflow 3** — zero new credentials, exercises
   scheduler → approval → file_write end to end on the owner's machine.
2. **Add Workflows 1–2 as draft generators** — still zero credentials;
   the human pastes copy into Shopify/Meta admin manually (which is also
   the safest pilot posture: no write API on a live store in week one).
3. **Only after a successful manual pilot**: Shopify Admin API provider
   (custom app, `products:write`, staff-facing approval) and Meta Ads API
   provider (system-user token, `ads_management`) — each behind the same
   ledger + one-time grant gate as `social_post`, each requiring real
   credentials and app-review work enumerated in `docs/PROGRESS.md`
   (risks #1–#3).

Explicitly out of scope by policy: no automated price changes, no
auto-publishing of ads, no credential storage outside `desktop/.env` +
the 0600 `~/.aion` vault pattern.
