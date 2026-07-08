---
name: hsg-rag-stakeholder-comms
description: How to communicate with the four external parties this project depends on — HSG-IT (DNS/zone changes), the EMBA web team (WordPress iframe embedding), the Datenschutzbeauftragte:r (GDPR sign-off), and advisors/EMBA marketing (contact/Calendly changes). Load when drafting a request to any of these parties, when the user says "schreib eine E-Mail an IT/Webteam/DSB", when an iframe embed fails on the target page, when DNS/CAA records are needed, when advisor contact data must change, or when deciding WHO must be contacted for a given failure. Contains proven German templates.
---

# HSG-RAG Stakeholder Communications

**As of 2026-07-07.** This project is not self-contained: production depends on
four external parties who do not read this repo. Every request to them must be
**self-contained and executable without project context**. This skill holds the
formats that have actually worked, plus verification steps so you never send an
unverified claim.

Language rule: skill text and your reasoning in English; **everything you send
to these parties is written in German** (all recipients are German-speaking).
Sign e-mails with the maintainer's name, not as an AI.

## The four parties

| Party | Owns | Typical request | Never ask them for |
|---|---|---|---|
| **HSG-IT** | DNS zone `unisg.ch`, CAA records | DNS records for `chatbot.emba.unisg.ch` | Server/app changes (we own the host) |
| **EMBA web team** | WordPress on `emba.unisg.ch` (non-technical operators) | Embed/adjust the chatbot iframe | Anything requiring code or DNS knowledge |
| **DSB** (Datenschutzbeauftragte:r) | GDPR sign-off (go-live blocker, checklist §2) | Review/sign-off of processing decisions | Technical implementation choices |
| **Advisors / EMBA marketing** | Advisor names, e-mails, phones, Calendly links | Confirm/update contact data | — (they provide data; changes are OUR code changes) |

## Escalation matrix — which failure goes to whom

| Symptom | Party | What to include |
|---|---|---|
| Domain does not resolve (`dig +short A chatbot.emba.unisg.ch` empty) | HSG-IT | The exact record specs (below) |
| TLS certificate errors after a zone change | HSG-IT | Ask whether a CAA record was added; it must allow `letsencrypt.org` |
| Iframe blank on `emba.unisg.ch` | EMBA web team first (console error?), then us (Caddyfile allowlist) | Troubleshooting path below |
| New embedding domain wanted | Us (Caddyfile `frame-ancestors` change via change-control), then web team | — |
| Advisor left / new Calendly link | Advisors/marketing supply data → **code change** via `hsg-rag-change-control` | Field template below |
| Any question about lawfulness of data processing | DSB | Facts from `docs/datenschutz_deployment.md`, never improvised claims |

---

## 1. HSG-IT — DNS and zone requests

Context: HSG-IT admins execute tickets; they do not know this project. A request
that requires follow-up questions loses days. The following format was sent and
executed successfully on 2026-07-07 (records live, TLS issued automatically).

Template (German) — adapt values only if the host changes:

```text
Betreff: DNS-Einträge für den Chatbot der EMBA-Website

für den Chatbot der EMBA-Website benötigen wir bitte zwei DNS-Einträge:

Eintrag 1
- Typ: A
- Name: chatbot.emba.unisg.ch
- Wert: 178.105.196.130
- TTL: Standard (3600)

Eintrag 2
- Typ: AAAA
- Name: chatbot.emba.unisg.ch
- Wert: 2a01:4f8:c014:9702::1
- TTL: Standard (3600)

Zusätzlich: Falls auf der Zone ein CAA-Record existiert, erlaubt dieser
letsencrypt.org? Der Server bezieht seine TLS-Zertifikate automatisch über
diesen Dienst.
```

Rules that made this work:
- One record per block, exact field names (Typ/Name/Wert/TTL) — the admin can
  copy them into any DNS console without interpretation.
- Ask the CAA question **proactively**; a forbidding CAA record silently breaks
  certificate issuance and is invisible from our side until Caddy fails.
- Status 2026-07-07: no CAA record exists on the zone. That is fine (no CAA =
  any CA may issue). **Open nice-to-have:** ask HSG-IT for
  `chatbot.emba.unisg.ch. CAA 0 issue "letsencrypt.org"` as hardening.

Verify after they confirm:

```bash
dig +short A chatbot.emba.unisg.ch      # expect: 178.105.196.130
dig +short AAAA chatbot.emba.unisg.ch   # expect: 2a01:4f8:c014:9702::1
curl -sf https://chatbot.emba.unisg.ch/health   # expect: {"status":"ok",...}
```

## 2. EMBA web team — iframe embedding

Context: they operate WordPress and are **not technical**. Give them numbered
steps, one exact snippet, and a self-service test script. The full proven
e-mail (sent 2026-07-07) is in
[references/iframe-embed-email.de.md](references/iframe-embed-email.de.md) —
send that; the summary below is for YOUR understanding.

The snippet (do not vary it when communicating):

```html
<iframe
  src="https://chatbot.emba.unisg.ch"
  title="EMBA HSG Chatbot"
  style="width:100%; height:800px; border:none;"
  loading="lazy"
  allow="clipboard-write"
></iframe>
```

Three preconditions — if any is violated the frame stays blank:

1. **Page must be served from `https://*.unisg.ch`, `https://embax.ch`, or
   `https://*.embax.ch`.** The server sends
   `Content-Security-Policy: frame-ancestors https://*.unisg.ch https://embax.ch https://*.embax.ch`
   (source of truth: [deploy/Caddyfile](../../../deploy/Caddyfile)). Staging
   domains of their hoster will be blocked by the browser — that is intended,
   not a bug. Testing must happen on the real domain.
2. **No `sandbox` attribute** on the iframe. The bot loads a nested Calendly
   iframe for booking and needs JavaScript; sandbox breaks both.
3. **Height ≥ 650 px (recommend 800 px).** Consent screen + chat + a ~650 px
   booking widget unfold inside the frame; scrolling happens inside it.

Functional test script to include (they can self-verify):
1. Load the page (also once in a private window).
2. Consent screen appears inside the frame → click "Akzeptieren".
3. Ask "Was kostet der EMBA?" → substantive answer must appear.
4. Write "Ich möchte einen Beratungstermin vereinbaren." → collapsible booking
   widget must appear under the chat.
5. Switch language to English at the top, ask one English question.

Troubleshooting path (put this in every embed e-mail): frame blank → open
browser console (F12) → if the message mentions `frame-ancestors` or
`X-Frame-Options`, the page is not on an allowed domain → they send us the
exact page URL → we extend the allowlist in `deploy/Caddyfile` (a code change:
route through `hsg-rag-change-control`; apply with
`systemctl reload caddy` on the host — no rebuild).

## 3. DSB — GDPR sign-off (the last go-live blocker)

Context: the DSB signs off checklist §2. Everything you assert to them must
come from [docs/datenschutz_deployment.md](../../../docs/datenschutz_deployment.md)
(status 2026-07-07: **Entwurf, kein Sign-off**). Never improvise privacy claims.

What already exists (verified in repo):
- Consent gate before any chat (`src/apps/chat/app.py`; decline path points
  users to `emba@unisg.ch`).
- User inputs redacted in the `agent_chain` log lines (only lengths logged;
  `_redact_user_text`, `src/rag/agent_chain.py`). **KNOWN OPEN GAP — do not
  present masking as complete:** `src/apps/chat/app.py:285` still logs the
  first 100 characters of each raw user query. Before sign-off this must be
  either fixed in code or explicitly disclosed to the DSB; a memo claiming
  "only lengths logged" would be false. (Same gap documented in
  `hsg-rag-architecture-contract` invariant I5 and `hsg-rag-run-and-operate` §7.)
- User profiles (`logs/user_profiles/`) deleted after 30 days (host cron);
  logs rotate after 30 days; Hetzner backups rotate after 7 days.
- Active deletion path `wipe_session_data` (`src/rag/agent_chain.py:467`).
- EU host (Hetzner Falkenstein) + Weaviate Cloud EU cluster.

What needs THEIR decision/signature (do not present as done):
- Weaviate Cloud AVV/DPA — signature pending.
- **Documented decision** that user inputs are processed by OpenRouter (USA),
  or the alternative (EU hosting, e.g. Azure OpenAI EU + no-training DPA).
- Hetzner AVV confirmation; final sign-off.

Decision-memo structure the DSB needs (write it FOR them, in German):
1. Sachverhalt — what data flows to OpenRouter (user messages, no
   registration data; anonymous sessions).
2. Optionen — (a) accept US processing with transparency notice, (b) migrate
   LLM to EU hosting; include effort/latency implications honestly.
3. Empfehlung + Begründung.
4. Unterschrift/Datum.

## 4. Advisors / EMBA marketing — contact data changes

Advisor data is **code**, not config: `ADVISOR_CONTACTS` in
[src/const/data_consent_constants.py](../../../src/const/data_consent_constants.py)
(and mirrored in `src/const/agent_response_constants.py` and
`data/database/programme_facts.json` via the facts pipeline — grep for the
name before editing). The current advisor table (names, e-mails, phones,
Calendly links) has one home: `emba-domain-reference` §4 (backed by
`ADVISOR_CONTACTS` in code) — read it there; do not maintain a copy here.

When marketing announces a change, collect ALL fields in one round (German):

```text
Für die Umstellung im Chatbot benötigen wir bitte vollständig:
- Programm (EMBA HSG / IEMBA HSG / emba X):
- Name der Beraterin / des Beraters:
- E-Mail (@unisg.ch):
- Telefon (Format +41 71 ...):
- Calendly-Link für Beratungsgespräche:
- Ab wann gilt die Änderung?
```

Then route the edit through `hsg-rag-change-control` (it is a production
deploy) and verify the booking flow afterwards (a booking-intent question must
show the new advisor).

## When NOT to use this skill

- Making the code/config change a stakeholder request results in → `hsg-rag-change-control`.
- The iframe/CSP mechanics themselves (header semantics, Caddy) → `hsg-rag-run-and-operate`.
- Diagnosing WHY something is broken before knowing whom to contact → `hsg-rag-debugging-playbook`.
- GDPR architecture facts in depth → `docs/datenschutz_deployment.md` (doc of record) and `hsg-rag-architecture-contract`.
- Improving conversion/answer quality → `hsg-rag-conversion-campaign`.

## Provenance and maintenance

Written 2026-07-07 from the live deployment session (DNS request executed by
HSG-IT the same day; iframe instructions sent to the web team; DSB sign-off
still open). Re-verify before relying on volatile facts:

```bash
grep -n "frame-ancestors" deploy/Caddyfile                      # CSP allowlist
sed -n '/ADVISOR_CONTACTS/,/^]/p' src/const/data_consent_constants.py  # advisors
dig +short A chatbot.emba.unisg.ch                              # DNS still 178.105.196.130
grep -n "Status" docs/datenschutz_deployment.md | head -2       # DSB sign-off status
```

If an advisor, domain, or the CSP allowlist changed, update the matching
template here in the same PR.
