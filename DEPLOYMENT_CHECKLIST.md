# Deployment Checklist — EMBA HSG RAG Chatbot

**Stand:** 2026-07-04 (Abschnitte 0/3/5/7 an den Ist-Zustand angepasst; ursprünglich 2026-06-16 @ `b0f8038`)
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
                  ├─ Weaviate Cloud (EU-Region)                 Retrieval
                  ├─ OpenRouter gpt-4.1                          Agent (alle LLM-Rollen, config.py)
                  └─ OpenRouter text-embedding-3-small           Embeddings (app-seitig)

GitHub Actions (kein Host-Cron nötig):
   update_programme_facts.yml   täglich 06:23 UTC   (verifizierte Fakten + Diff-Alerts)
   scrape.yml                   wöchentlich So 05:17 UTC
   NOTIFY_*-Secrets sind im Repo hinterlegt (Alerts laufen aus der Action)
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

- [x] **PR #41 (Caching-Entfernung) gemergt** — `src/cache/` existiert nicht mehr in `main`.
- [ ] `requirements.txt` entspricht dem tatsächlichen Runtime-Bedarf
- [ ] Dockerfile-Base-Image aktuell ([Dockerfile](Dockerfile): `python:3.11.14-slim-bookworm` ✓)
- [ ] Offline-Tests grün: `pytest tests/test_verified_facts.py tests/test_stream_parser.py`
- [ ] Vor Release: `RUN_LLM_EVAL=1 pytest tests/test_llm_fact_eval.py -v` → **31/31**

---

## 4. Weaviate (PR #40 abschließen)

- [x] EU-Cluster bereitgestellt, `.env`: `WEAVIATE_CLUSTER_URL` + `WEAVIATE_API_KEY` gesetzt
- [x] `python main.py --weaviate checkhealth` → Connection ✓ OK
- [x] `python main.py --weaviate init` → Collections `hsg_rag_content_de`/`_en` angelegt
- [ ] **Datenimport abgeschlossen:** `python main.py --scrape full`
      (läuft; danach Objekt-Counts in beiden Collections plausibel prüfen — EN/embax nicht unterrepräsentiert)
- [ ] `python main.py --weaviate checkhealth` → beide Collections ✓ OK
- [ ] Stichprobe: Query "Was macht die HSG besonders?" liefert echte Chunks (keine `QUERY_EXCEPTION_MESSAGE`)

---

## 5. Umgebungsvariablen (Prod-`.env`)

- [ ] `OPEN_ROUTER_API_KEY` (**alle** LLM-Rollen + Embeddings — seit PR #49 läuft nichts mehr direkt über OpenAI)
- [ ] `WEAVIATE_CLUSTER_URL`, `WEAVIATE_API_KEY` (EU-Cluster)
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
- [ ] `<iframe src="https://bot.hsg.ch">` auf einer EMBA-Testseite einbauen
- [ ] Cross-Origin-Test: Bot lädt **auf der Zielseite** (nicht nur standalone)

---

## 7. Zeitgesteuerte Tasks (laufen als GitHub Actions — kein Host-Cron nötig)

- [x] **Verifizierte Fakten**: `.github/workflows/update_programme_facts.yml`, täglich 06:23 UTC —
      läuft und ist grün (geprüft 2026-07-04; NOTIFY_*-Secrets im Repo hinterlegt)
- [x] **Scraping-Refresh**: `.github/workflows/scrape.yml`, wöchentlich So 05:17 UTC — läuft
- [ ] **Alert-Chain einmal end-to-end testen:** Preis in `data/database/programme_facts.json` ändern →
      Workflow manuell triggern (`gh workflow run update_programme_facts.yml`) →
      E-Mail/Slack muss ankommen → Änderung zurücknehmen
- [x] ~~`HUGGING_FACE_API_KEY` erneuern~~ — **entfällt** (geprüft 2026-07-06): Der Key wird
      nirgends gebraucht. Der 401 kam von einem abgelaufenen lokalen HF-Login; ohne Token laden
      die Docling-Modelle anonym. Für die Fee-Sheet-PDFs liefert ohnehin pypdf den echten Text
      (Docling sieht nur Bilder); `extract_pdf_text` fällt bei Docling-Leerergebnis jetzt
      automatisch auf pypdf zurück. GitHub-Secret + `.env`-Eintrag können gelöscht werden.
- [ ] Veralteten Cron auf dem Dev-Mac entfernen (`crontab -e`) — crasht täglich an macOS-TCC
      (`failed to make path absolute`) und ist durch die GitHub Action ersetzt

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

- [ ] Facts-Action wöchentlich prüfen (`gh run list --workflow=update_programme_facts.yml`) —
      laufen die Runs durch, sind Diffs plausibel?
- [ ] `grep "\[timing\]" logs/logs.log` — Latenz im Blick (Ziel ~6 s end-to-end)
- [ ] Weaviate-Cluster-Status (läuft, nicht abgelaufen — Lehre aus dem 404-Ausfall)
- [ ] Health-Check `GET /health` in Host-Monitoring eingebunden

---

## Go / No-Go

**Go**, wenn: Host in EU/CH steht · Datenschutz-Sign-off · Weaviate gefüllt & checkhealth grün ·
iframe-CSP gefixt & auf Zielseite getestet · beide GitHub Actions grün & Alert getestet · Smoke-Tests grün.

**No-Go**, wenn: kein DSGVO-Sign-off · Weaviate leer/abgelaufen · CSP blockiert iframe auf `*.unisg.ch` ·
SMTP/Slack fehlt (Fakten-Alerts stumm) · LLM-Eval nicht 31/31.
