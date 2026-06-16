# Deployment Checklist — EMBA HSG RAG Chatbot

**Stand:** 2026-06-16 · **Branch/Commit:** `main` @ `b0f8038`
**Ablöst:** [docs/deploy_readiness_checklist.md](docs/deploy_readiness_checklist.md) (vom 10.04., in Teilen veraltet — siehe Abschnitt 7)

Ziel: Single-Host-Deployment des Bots, eingebettet per `<iframe>` in die EMBA-Website
(`emba.unisg.ch` / `embax.ch`), DSGVO-bewusst in EU/CH gehostet.

---

## 0. Architektur (Ist-Zustand im Code)

```
Browser auf emba.unisg.ch / embax.ch
   └─ <iframe src="https://bot.hsg.ch">
        └─ Caddy (TLS, reverse proxy, CSP)        deploy/Caddyfile
             └─ Container: python main.py --app de   →  0.0.0.0:7860  (Gradio/FastAPI, /health)
                  ├─ Weaviate Cloud (EU-Region)        Retrieval
                  ├─ OpenAI gpt-4.1                     Agent
                  └─ OpenRouter text-embedding-3-small  Embeddings (app-seitig)

Cron auf demselben Host:
   0 6 * * *   update_programme_facts   (verifizierte Fakten + Diff-Alerts)
   Scrape-Refresh (inkrementell tgl. / voll wöchentlich)
```

---

## 1. Host & Infrastruktur (BLOCKER — mit HSG-IT klären)

- [ ] **Host-Eigentümer von `bot.hsg.ch` geklärt** — wer betreibt die Domain/DNS?
- [ ] **Linux-Host in EU/CH bereitgestellt** (DSGVO) — entweder HSG-IT-VM oder eigener EU-Cloud-VM (Hetzner/Exoscale/Swisscom …)
- [ ] **Docker + Caddy + Cron auf dem Host erlaubt** (von HSG-IT bestätigt)
- [ ] **DNS:** `bot.hsg.ch` zeigt auf den Ziel-Host
- [ ] Port **7860** intern auf dem Host erreichbar (nur lokal; nach außen nur via Caddy/443)
- [ ] Ausgehender Netzzugang zu: Weaviate Cloud, `api.openai.com`, `openrouter.ai`, SMTP/Slack

> **Entscheidungsfrage an HSG-IT:** "Wer betreibt `bot.hsg.ch`, stellt ihr uns einen Linux-Host
> in EU/CH, und dürfen wir dort Docker + Caddy + Cron betreiben?" Davon hängt der Rest ab.

---

## 2. Datenschutz / EU (vor Go-Live entscheiden)

- [ ] **Weaviate Cloud in EU-Region** (Frankfurt `europe-west3` o.ä.) + **AVV/DPA** unterschrieben
- [ ] **Bewusste Entscheidung dokumentiert**, dass **OpenAI (US)** und **OpenRouter (US)** Nutzer-Eingaben
      verarbeiten — bei echtem EU-Konformitätsanspruch auf EU-Hosting umstellen
      (z. B. Azure OpenAI EU-Region + No-Training-DPA, EU-gehostetes Embedding-Modell)
- [ ] **Nutzerprofile** (`logs/user_profiles/`) liegen lokal auf dem Host — Aufbewahrung/Löschung
      (GDPR-Withdrawal-Pfad `wipe_session_data` existiert) und Backup-Policy geklärt
- [ ] Consent-Flow im UI vor Go-Live verifiziert
- [ ] Sign-off durch Datenschutzbeauftragte:n

---

## 3. Repo-Stand & Code (vor Build)

- [ ] **PR #41/#42 (Caching-Entfernung)** entscheiden: mergen oder schließen.
      Aktuell **nicht in `main`** — `main` importiert noch `src/cache/`. Redis ist optional
      (Fallback auf dict-Cache, Redis-Verbindungsfehler ist unkritisch).
- [ ] `requirements.txt` entspricht dem tatsächlichen Runtime-Bedarf
- [ ] Dockerfile-Base-Image aktuell ([Dockerfile](Dockerfile): `python:3.11.14-slim-bookworm` ✓)
- [ ] Offline-Tests grün: `pytest tests/test_verified_facts.py tests/test_stream_parser.py`
- [ ] Vor Release: `RUN_LLM_EVAL=1 pytest tests/test_llm_fact_eval.py -v` → **31/31**

---

## 4. Weaviate (PR #40 abschließen)

- [x] EU-Cluster bereitgestellt, `.env`: `WEAVIATE_CLUSTER_URL` + `WEAVIATE_API_KEY` gesetzt
- [x] `python main.py --weaviate checkhealth` → Connection ✓ OK
- [x] `python main.py --weaviate init` → Collections `hsg_rag_content_de`/`_en` angelegt
- [ ] **Datenimport abgeschlossen:** `python main.py --scrape --full_scrape`
      (läuft; danach Objekt-Counts in beiden Collections plausibel prüfen — EN/embax nicht unterrepräsentiert)
- [ ] `python main.py --weaviate checkhealth` → beide Collections ✓ OK
- [ ] Stichprobe: Query "Was macht die HSG besonders?" liefert echte Chunks (keine `QUERY_EXCEPTION_MESSAGE`)

---

## 5. Umgebungsvariablen (Prod-`.env`)

- [ ] `OPENAI_API_KEY` (Agent gpt-4.1)
- [ ] `OPEN_ROUTER_API_KEY` (Embeddings)
- [ ] `WEAVIATE_CLUSTER_URL`, `WEAVIATE_API_KEY` (EU-Cluster)
- [ ] **SMTP/Slack-Variablen** für Fakten-Änderungs-Alerts (sonst läuft der Facts-Cron ohne Benachrichtigung)
- [ ] Optional `LANGSMITH_*` (Tracing)
- [ ] Werte gegen `src/config/configs.py` verifiziert

---

## 6. iframe-Integration ⚠️

- [ ] **CSP im [deploy/Caddyfile](deploy/Caddyfile) korrigieren.** Aktuell:
      `frame-ancestors https://*.hsg.ch` — das **blockiert** die Einbettung auf
      `emba.unisg.ch` / `embax.ch` (andere Domains!). Anpassen auf die tatsächlichen
      Einbettungs-Domains, z. B.:
      `header Content-Security-Policy "frame-ancestors https://*.unisg.ch https://embax.ch"`
- [ ] Einbettungs-Domains mit dem EMBA-Webteam final abstimmen
- [ ] `<iframe src="https://bot.hsg.ch">` auf einer EMBA-Testseite einbauen
- [ ] Cross-Origin-Test: Bot lädt **auf der Zielseite** (nicht nur standalone)

---

## 7. Cron-Tasks (auf dem Deploy-Host)

- [ ] **Verifizierte Fakten** — täglich 06:00:
      ```
      0 6 * * * cd <repo> && ./venv/bin/python -m src.pipeline.update_programme_facts >> logs/fact_update.log 2>&1
      ```
- [ ] **Scraping-Refresh** — als Cron (robuster als Dauerprozess):
      ```
      0 3 * * 1-6 cd <repo> && ./venv/bin/python main.py --scrape              >> logs/scrape.log 2>&1
      0 2 * * 0   cd <repo> && ./venv/bin/python main.py --scrape --full_scrape >> logs/scrape.log 2>&1
      ```
      (Alternative: `python tools/scraping.py --init_sched` als systemd-Service — APScheduler intern.)
- [ ] **Alert-Chain einmal testen:** Preis in `data/database/programme_facts.json` ändern →
      `python -m src.pipeline.update_programme_facts` → E-Mail/Slack muss ankommen → Änderung zurücknehmen

---

## 8. Build & Rollout

- [ ] Image bauen aus gemergetem `main`
- [ ] Image-Vulnerability-Scan gegen neues Digest
- [ ] Schreibbare Runtime-Pfade auf dem Host: `logs/`, `data/`, `backups/`
- [ ] Container starten (`0.0.0.0:7860`), Caddy mit `deploy/Caddyfile` davor
- [ ] `python main.py --weaviate checkhealth` auf dem Host

---

## 9. Funktions-Smoke-Tests (über die öffentliche Domain)

- [ ] Bot über `https://bot.hsg.ch` und **als iframe** auf der EMBA-Seite erreichbar
- [ ] Consent-Flow
- [ ] DE- und EN-Antworten
- [ ] Retrieval aus Weaviate (Programm-/USP-Fragen liefern echte Inhalte)
- [ ] Admissions-Handover-Pfad
- [ ] Booking-Widget erscheint korrekt

---

## 10. Betrieb / Monitoring

- [ ] `logs/fact_update.log` wöchentlich prüfen — laufen die Cron-Runs durch, sind Diffs plausibel?
- [ ] `grep "\[timing\]" logs/logs.log` — Latenz im Blick (Ziel ~6 s end-to-end)
- [ ] Weaviate-Cluster-Status (läuft, nicht abgelaufen — Lehre aus dem 404-Ausfall)
- [ ] Health-Check `GET /health` in Host-Monitoring eingebunden

---

## Go / No-Go

**Go**, wenn: Host in EU/CH steht · Datenschutz-Sign-off · Weaviate gefüllt & checkhealth grün ·
iframe-CSP gefixt & auf Zielseite getestet · beide Cron-Tasks aktiv & Alert getestet · Smoke-Tests grün.

**No-Go**, wenn: kein DSGVO-Sign-off · Weaviate leer/abgelaufen · CSP blockiert iframe auf `*.unisg.ch` ·
SMTP/Slack fehlt (Fakten-Alerts stumm) · LLM-Eval nicht 31/31.
