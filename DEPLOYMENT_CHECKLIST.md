# Deployment Checklist — EMBA HSG RAG Chatbot

**Stand:** 2026-07-07 (DNS/TLS live, Smoke-Tests grün, Streaming-Fix deployt, Auto-Deploy eingerichtet; ursprünglich 2026-06-16 @ `b0f8038`)
**Ablöst:** [docs/deploy_readiness_checklist.md](docs/deploy_readiness_checklist.md) (vom 10.04., in Teilen veraltet — siehe Abschnitt 7)

Ziel: Single-Host-Deployment des Bots, eingebettet per `<iframe>` in die EMBA-Website
(`emba.unisg.ch` / `embax.ch`), DSGVO-bewusst in EU/CH gehostet.

---

## 0. Architektur (Ist-Zustand im Code)

```
Browser auf emba.unisg.ch / embax.ch
   └─ <iframe src="https://chatbot.emba.unisg.ch">
        └─ Caddy (TLS, reverse proxy, CSP)        deploy/Caddyfile
             └─ Container: python main.py --app de   →  0.0.0.0:7860  (Gradio/FastAPI, /health)
                  ├─ Weaviate Cloud (EU-Region)                 Retrieval
                  ├─ OpenRouter gpt-4.1                          Agent (alle LLM-Rollen, config.py)
                  └─ OpenRouter text-embedding-3-small           Embeddings (app-seitig)

GitHub Actions (kein Host-Cron nötig):
   update_programme_facts.yml   täglich 06:23 UTC   (verifizierte Fakten + Diff-Alerts)
   scrape.yml                   wöchentlich So 05:17 UTC
   deploy.yml                   Auto-Deploy: Push auf main, nach jedem Facts-Lauf,
                                manuell (rsync → Build → Container neu → Health-Checks;
                                Rollback-Anker: Image-Tag hsg-rag:previous)
   NOTIFY_*-Secrets sind im Repo hinterlegt (Alerts laufen aus der Action)
```

---

## 1. Host & Infrastruktur (BLOCKER — mit HSG-IT klären)

- [x] **Linux-Host in EU/CH bereitgestellt** (2026-07-06): Hetzner CPX32, Falkenstein (fsn1),
      Ubuntu 24.04, `hsg-rag-prod-fsn1-1` (178.105.196.130) — Docker + Caddy installiert,
      SSH gehärtet, unattended-upgrades + Backups aktiv, Cloud-Firewall (nur 22/80/443 offen)
- [x] **DNS:** `chatbot.emba.unisg.ch` → `178.105.196.130` (A) + `2a01:4f8:c014:9702::1` (AAAA)
      — **von HSG-IT gesetzt (2026-07-07)**, löst extern auf (IPv4 + IPv6). Kein CAA-Record
      auf der Zone = unkritisch (ohne CAA darf jede CA ausstellen). Let's-Encrypt-Zertifikat
      wurde von Caddy automatisch bezogen (gültig bis 2026-10-05, Auto-Renewal)
- [x] Port **7860** nur auf 127.0.0.1 gebunden (nach außen nur via Caddy/443) — geprüft 2026-07-06
- [x] Ausgehender Netzzugang zu Weaviate Cloud + `openrouter.ai` verifiziert (Bot antwortet live)

---

## 2. Datenschutz / EU (vor Go-Live entscheiden)

- [ ] **Weaviate Cloud in EU-Region** (Frankfurt `europe-west3` o.ä.) + **AVV/DPA** unterschrieben
- [ ] **Bewusste Entscheidung dokumentiert**, dass **OpenAI (US)** und **OpenRouter (US)** Nutzer-Eingaben
      verarbeiten — bei echtem EU-Konformitätsanspruch auf EU-Hosting umstellen
      (z. B. Azure OpenAI EU-Region + No-Training-DPA, EU-gehostetes Embedding-Modell)
- [x] **Nutzerprofile** (`logs/user_profiles/`): Aufbewahrung geregelt (2026-07-06) —
      30-Tage-Löschfrist per Host-Cron, Logs rotieren nach 30 Tagen, Nutzereingaben in Logs
      maskiert, Backup-Rotation 7 Tage. Details: [docs/datenschutz_deployment.md](docs/datenschutz_deployment.md)
- [ ] Consent-Flow im UI vor Go-Live verifiziert
- [ ] **Usage-Analytics-Retention auf dem Host eingerichtet**: Lösch-Cron um die neuen
      Verzeichnisse erweitern —
      `find /opt/hsg-rag/logs/usage /opt/hsg-rag/logs/transcripts -name '*.jsonl' -mtime +30 -delete`
      (Details: [docs/datenschutz_deployment.md](docs/datenschutz_deployment.md) §4)
- [ ] **Transkript-Speicherung erst nach DSB-Sign-off aktivieren**: `USAGE_STORE_TRANSCRIPTS=true`
      in der Prod-`.env` + Container-Neustart — Voraussetzung ist Consent-Text v1.1
- [ ] **Ersten Wochenbericht verifiziert**: "Weekly Usage Report"-Workflow einmal manuell
      auslösen (`gh workflow run usage-report.yml`); der committete Report in `docs/usage-reports/`
      enthält nur Aggregate (keine Session-IDs) und löst keinen Deploy aus
- [ ] Sign-off durch Datenschutzbeauftragte:n

---

## 3. Repo-Stand & Code (vor Build)

- [x] **PR #41 (Caching-Entfernung) gemergt** — `src/cache/` existiert nicht mehr in `main`.
- [x] `requirements.txt` entspricht dem tatsächlichen Runtime-Bedarf (Audit 2026-07-07:
      alle Third-Party-Imports gedeckt — direkt, transitiv via gradio/langchain oder als
      dokumentierte Lazy-Imports in `src/rag/models.py`)
- [ ] Dockerfile-Base-Image aktuell ([Dockerfile](Dockerfile): `python:3.11.14-slim-bookworm` ✓)
- [x] Offline-Tests grün: `pytest tests/test_verified_facts.py tests/test_stream_parser.py`
      (2026-07-07: 73/73, inkl. Streaming-Fix PR #67)
- [x] Vor Release: `RUN_LLM_EVAL=1 pytest tests/test_llm_fact_eval.py -v` → **31/31** (2026-07-07, 160 s)

---

## 4. Weaviate (PR #40 abschließen)

- [x] EU-Cluster bereitgestellt, `.env`: `WEAVIATE_CLUSTER_URL` + `WEAVIATE_API_KEY` gesetzt
- [x] `python main.py --weaviate checkhealth` → Connection ✓ OK
- [x] `python main.py --weaviate init` → Collections `hsg_rag_content_de`/`_en` angelegt
- [x] **Datenimport abgeschlossen** (verifiziert 2026-07-07): `hsg_rag_content_de` 227 Objekte,
      `hsg_rag_content_en` 144 Objekte. embax.ch: 12 EN-Objekte, 0 DE — plausibel, da
      embax.ch englischsprachig ist; deutschsprachiger emba-X-Content kommt über
      `emba.unisg.ch`-Artikel in die DE-Collection
- [x] `python main.py --weaviate checkhealth` → beide Collections ✓ OK (2026-07-07)
- [x] Stichprobe: "Was macht die HSG besonders?" liefert echte Chunks — über die
      öffentliche Prod-Domain verifiziert (Smoke-Tests, Abschnitt 9)

---

## 5. Umgebungsvariablen (Prod-`.env`)

- [x] `OPEN_ROUTER_API_KEY` (**alle** LLM-Rollen + Embeddings — seit PR #49 läuft nichts mehr direkt über OpenAI)
      — auf dem Host in `/opt/hsg-rag/.env` (chmod 600), Bot antwortet live damit
- [x] `WEAVIATE_CLUSTER_URL`, `WEAVIATE_API_KEY` (EU-Cluster) — gesetzt, `/health` meldet `weaviate: true`
- [ ] Optional `LANGSMITH_*` (Tracing)
- [ ] Werte gegen `src/config/configs.py` verifiziert (Vorlage: `.env.example`)

> `OPENAI_API_KEY` wird zur Laufzeit **nicht** mehr gebraucht — nur die opt-in
> Test-Suiten (`RUN_LLM_EVAL`, `RUN_UAT_LLM_JUDGE`) nutzen ihn.
> `NOTIFY_*` (SMTP/Slack) liegt als GitHub-Secrets bei der Facts-Action — auf dem
> App-Host nur nötig, falls der Host selbst Alerts verschicken soll.

---

## 6. iframe-Integration ⚠️

- [x] **CSP im [deploy/Caddyfile](deploy/Caddyfile) korrigiert** (2026-07-04):
      `frame-ancestors https://*.unisg.ch https://embax.ch https://*.embax.ch`
      (vorher `https://*.hsg.ch` — hätte die Einbettung auf den Zielseiten blockiert)
- [ ] Einbettungs-Domains mit dem EMBA-Webteam final abstimmen
- [ ] `<iframe src="https://chatbot.emba.unisg.ch">` auf einer EMBA-Testseite einbauen
- [ ] Cross-Origin-Test: Bot lädt **auf der Zielseite** (nicht nur standalone)

---

## 7. Zeitgesteuerte Tasks (laufen als GitHub Actions — kein Host-Cron nötig)

- [x] **Verifizierte Fakten**: `.github/workflows/update_programme_facts.yml`, täglich 06:23 UTC —
      läuft und ist grün (geprüft 2026-07-04; NOTIFY_*-Secrets im Repo hinterlegt)
- [x] **Scraping-Refresh**: `.github/workflows/scrape.yml`, wöchentlich So 05:17 UTC — läuft
- [x] **Alert-Chain end-to-end getestet (2026-07-07):** EMBA-Gebühr testweise auf 77'000 gesetzt →
      Workflow-Run 28864823526: Diff erkannt (`fee: 77000 -> 77500`),
      `Change notification dispatched (email + slack)`, korrigierte Datei automatisch
      zurückcommittet (`be9cc80`), anschließend `workflow_run`-Auto-Deploy gelaufen,
      Prod antwortet wieder mit CHF 77'500. Sichtprüfung Posteingang/Slack: DK
- [x] ~~`HUGGING_FACE_API_KEY` erneuern~~ — **entfällt** (2026-07-06): Pipeline/Runtime brauchen
      keinen HF-Key (Docling-Modelle laden anonym; bei Docling-Leerergebnis greift der
      pypdf-Fallback in `extract_pdf_text`). Der einzige Verbraucher war der
      HF-Space-Sync-Workflow (`sync_to_huggingface.yml`) — dieser wurde mitsamt Space-Deployment
      **entfernt**, da das Produktiv-Deployment auf dem eigenen EU-Host läuft. Secret gelöscht.
- [x] Veralteten Cron auf dem Dev-Mac entfernen — erledigt: `crontab -l` ist leer (geprüft 2026-07-07)

---

## 8. Build & Rollout

- [x] Image gebaut auf dem Host (2026-07-06, `hsg-rag:latest`, 2.86 GB) — Code per rsync,
      `.env` mit nur 3 Runtime-Variablen (chmod 600)
- [x] Image-Vulnerability-Scan (Trivy, 2026-07-06): ein runtime-relevanter Befund —
      **gradio Cookie-Injection (CVE-2026-48545)** → Pin auf 6.15.0 angehoben;
      **Rescan nach Rebuild (2026-07-07): gradio 0 Findings** ✓. Neu im Base-Image:
      OpenSSL/GnuTLS/libcap2 mit verfügbaren Debian-Fixes (u. a. CVE-2026-31789) —
      geringe Exposition (nur ausgehende Verbindungen, Container hinter Caddy);
      erledigt sich über die täglichen Rebuilds, sobald die Patches im
      `python:3.11-slim`-Image ankommen
- [x] Schreibbare Runtime-Pfade: `logs/` als Host-Volume gemountet (persistiert Nutzerprofile)
- [x] Container läuft (Port nur 127.0.0.1:7860, `--restart unless-stopped`), Caddy aktiv
      mit [deploy/Caddyfile](deploy/Caddyfile) — TLS folgt automatisch, sobald DNS gesetzt ist
- [x] Health auf dem Host geprüft: `/health` → `status: ok, weaviate: true`
- [x] **Nach Gradio-Bump:** Image neu gebaut + deployt (2026-07-07), `/health` ✓,
      Gradio 6.15.0 im Container verifiziert
- [x] **Auto-Deploy eingerichtet (2026-07-07, PR #68):** `.github/workflows/deploy.yml` —
      Merge auf `main` = Deploy; zusätzlich nach jedem erfolgreichen Facts-Lauf
      (schließt die Lücke, dass `programme_facts.json` im Image eingebacken ist und
      Preisänderungen die Produktion sonst nie erreichen). Dedizierter Deploy-Key
      als Secret `DEPLOY_SSH_KEY`, Host-Key im Workflow gepinnt. Manuelle
      rsync-Deploys sind damit obsolet
- [x] **Streaming-Fix deployt (2026-07-07, PR #67):** `finish_reason`-Konkatenation
      unter Streaming ließ jeden Retrieval-Turn in den Blocking-Fallback laufen
      (12–14 s ohne sichtbare Tokens, 2 verworfene LLM-Calls). Jetzt: erstes Token
      ~4 s, gesamt ~6 s — Latenzziel wieder erreicht

---

## 9. Funktions-Smoke-Tests (über die öffentliche Domain)

Durchgeführt 2026-07-07 per Gradio-API gegen `https://chatbot.emba.unisg.ch` (echte Prod-Sessions):

- [x] Bot über `https://chatbot.emba.unisg.ch` erreichbar (IPv4 + IPv6, TLS ✓)
- [ ] **Als iframe auf der EMBA-Seite** — CSP-Header wird korrekt ausgeliefert
      (`frame-ancestors https://*.unisg.ch https://embax.ch https://*.embax.ch`),
      der Cross-Origin-Test braucht aber eine Testseite vom EMBA-Webteam (Abschnitt 6);
      Einbau-Anleitung wurde an das Webteam verschickt (2026-07-07)
- [x] Consent-Flow (Accept + Decline; Decline zeigt Hinweis mit `emba@unisg.ch`)
- [x] DE- und EN-Antworten (inkl. Sprachwechsel im UI)
- [x] Retrieval aus Weaviate (USP-Frage liefert echte Chunks; Preisantwort exakt
      gegen `programme_facts.json` verifiziert, abgelaufene Frühbucher-Frist korrekt erkannt)
- [x] Admissions-Handover-Pfad (Beratungsanfrage → korrekte Advisorin Cyra von Müller)
- [x] Booking-Widget erscheint korrekt (nach Accept und bei Terminanfrage)

---

## 10. Betrieb / Monitoring

- [ ] Facts-Action wöchentlich prüfen (`gh run list --workflow=update_programme_facts.yml`) —
      laufen die Runs durch, sind Diffs plausibel?
- [ ] `grep "\[timing\]" logs/logs.log` — Latenz im Blick (Ziel ~6 s end-to-end;
      Stand 2026-07-07 nach Streaming-Fix: Retrieval-Turns ~6 s, Fakten-Turns 2–3 s,
      erstes Token ~4 s. Warnzeichen im Log: `empty response` / `falling back to blocking`)
- [ ] Weaviate-Cluster-Status (läuft, nicht abgelaufen — Lehre aus dem 404-Ausfall)
- [ ] Health-Check `GET /health` in Host-Monitoring eingebunden

---

## Go / No-Go

**Go**, wenn: Host in EU/CH steht · Datenschutz-Sign-off · Weaviate gefüllt & checkhealth grün ·
iframe-CSP gefixt & auf Zielseite getestet · beide GitHub Actions grün & Alert getestet · Smoke-Tests grün.

**No-Go**, wenn: kein DSGVO-Sign-off · Weaviate leer/abgelaufen · CSP blockiert iframe auf `*.unisg.ch` ·
SMTP/Slack fehlt (Fakten-Alerts stumm) · LLM-Eval nicht 31/31.
