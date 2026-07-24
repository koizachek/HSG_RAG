# Datenschutz-Dokumentation — EMBA HSG Chatbot (ENTWURF)

**Stand:** 2026-07-06 · **Status: Entwurf zur Prüfung durch die/den Datenschutzbeauftragte:n — kein Sign-off**
Bezieht sich auf das Produktiv-Deployment `chatbot.emba.unisg.ch` (Hetzner, Falkenstein/DE)
gemäß [DEPLOYMENT_CHECKLIST.md](../DEPLOYMENT_CHECKLIST.md) §2.

---

## 1. Übersicht der Verarbeitung

Der Chatbot beantwortet Fragen zu den HSG-Executive-MBA-Programmen. Nutzer:innen
interagieren anonym über ein iframe auf `emba.unisg.ch` / `embax.ch`; es gibt keine
Registrierung und keine Zahlungsdaten.

## 2. Welche Daten gespeichert werden (auf dem EU-Host)

| Kategorie | Ort | Inhalt | Aufbewahrung |
|---|---|---|---|
| Nutzerprofile (Feature-Flag `TRACK_USER_PROFILE`) | `logs/user_profiles/*.json` | Session-/User-ID, ggf. Name (falls genannt), Berufs-/Führungsjahre, Branche, Interessen, vorgeschlagenes Programm, Handover-Wunsch, Sprache | **30 Tage** (täglicher Lösch-Cron auf dem Host) |
| Consent-Einträge | `logs/consent/` | Einwilligungsnachweis mit Zeitstempel | unbefristet (Nachweiszweck) |
| Technische Logs | `logs/*.log` | System-/Fehlermeldungen; **Nutzereingaben werden seit 2026-07-06 maskiert** (nur Länge geloggt, kein Wortlaut) | **30 Tage** (logrotate, komprimiert, dann gelöscht) |
| Nutzungs-Events (Flag `USAGE_EVENT_LOGGING_ENABLED`) | `logs/usage/*.jsonl` | Pseudonyme Metadaten pro Chat-Turn: Session-ID, Ergebnis-Typ, Booking-Flags, Programm-Zuordnung, Fehler-Marker, Antwortzeiten. **Keine Gesprächsinhalte** (nur Zeichenanzahl der Eingabe) | **30 Tage** (Lösch-Cron auf dem Host, siehe §4) |
| Gesprächsprotokolle (Flag `USAGE_STORE_TRANSCRIPTS`, **aktiv seit 2026-07-24**) | `logs/transcripts/*.jsonl` | Pseudonymisierte Transkripte (Nutzereingabe + Bot-Antwort) zur Offline-Qualitätsbewertung. Speicherung aktiviert zusammen mit Consent-Text v1.1; Aktivierung vor DSB-Sign-off auf Anforderung M. Li (E-Mail 24.07.2026). **Die Offline-Auswertung (Übermittlung von Stichproben an OpenRouter, USA) startet erst nach DSB-Sign-off** | **30 Tage** (Lösch-Cron auf dem Host, siehe §4) |
| Wochenberichte | `logs/usage_reports/`, Repo `docs/usage-reports/` | Ausschließlich anonyme Aggregate (Zählwerte, Raten, Perzentile) — keine Session-IDs, keine Inhalte | Host: ~26 Wochen; Repo: unbefristet (anonym) |

## 3. Verarbeitung durch Dritte (keine Speicherung durch uns)

| Dienst | Sitz | Zweck | Hinweis |
|---|---|---|---|
| **OpenRouter** (LLM gpt-4.1 + Embeddings) | **USA** | Beantwortung der Nutzernachrichten | Nutzereingaben werden zur Verarbeitung übermittelt. **Bewusste Entscheidung erforderlich/dokumentieren** (§2 Checkliste); Alternative bei striktem EU-Anspruch: Azure OpenAI EU-Region + No-Training-DPA |
| **Weaviate Cloud** | **EU** (Cluster in EU-Region) | Semantische Suche über öffentliche Programminhalte | AVV/DPA abschließen (§2 Checkliste); es werden Suchanfragen übermittelt, keine Profile |
| **LangSmith** | USA | Tracing/Debugging | **In Produktion deaktiviert** (Umgebungsvariablen nicht gesetzt) |
| Hetzner (Host + Backups) | DE | Betrieb, tägliche Server-Backups | AVV ist Vertragsbestandteil (Hetzner-Account) |

## 4. Löschung / Betroffenenrechte

- **Aktiver Löschpfad:** `wipe_session_data` (API in `src/rag/agent_chain.py`) entfernt
  Sitzungsdaten inkl. Profil-, Nutzungs-Event- und Transkript-Dateien der Session.
  **Hinweis:** Ein UI-Auslöser dafür existiert derzeit nicht — Löschanfragen laufen
  über den Kontaktweg (E-Mail) und werden manuell auf dem Host ausgeführt.
- **Automatische Fristen:** Nutzerprofile und Logs werden nach 30 Tagen serverseitig
  gelöscht. Der Lösch-Cron auf dem Host muss um die neuen Verzeichnisse erweitert werden:
  `find /opt/hsg-rag/logs/usage /opt/hsg-rag/logs/transcripts -name '*.jsonl' -mtime +30 -delete`
- **Backups:** Hetzner-Snapshots rotieren nach **7 Tagen**. Eine aktive Löschung wirkt in
  Backups nicht rückwirkend; faktische maximale Aufbewahrung nach Löschung: 7 Tage.

## 5. Technische Schutzmaßnahmen

- Transport: TLS via Caddy (Let's Encrypt), HTTP→HTTPS-Redirect
- Zugriff: Server nur per SSH-Key (Passwort-Login deaktiviert), Cloud-Firewall (nur 22/80/443),
  App-Port 7860 ausschließlich auf localhost gebunden
- Secrets: Prod-`.env` mit `chmod 600`, keine Secrets im Repo (`.gitignore`-Härtung),
  automatische Sicherheitsupdates (`unattended-upgrades`)
- Container: Nicht-öffentliches internes Netz, Auto-Restart, Health-Checks

## 6. Offene Punkte für das Sign-off

- [ ] Bewusste, dokumentierte Entscheidung: US-Verarbeitung durch OpenRouter akzeptieren
      oder auf EU-Hosting (z. B. Azure OpenAI EU) umstellen
- [ ] AVV/DPA mit Weaviate Cloud abschließen und ablegen
- [ ] Hetzner-AVV im Account bestätigen/ablegen
- [ ] Consent-Flow im UI auf der Zielseite verifizieren (nach DNS/iframe-Einbindung)
- [x] **Transkript-Speicherung freigegeben** (`USAGE_STORE_TRANSCRIPTS`, 2026-07-24):
      pseudonymisierte Gesprächsprotokolle (30 Tage, Host-only). Aktivierung zusammen mit
      Consent-Text v1.1, vor DSB-Sign-off auf Anforderung M. Li (E-Mail 24.07.2026)
- [ ] **Offline-Qualitätsbewertung freigeben**: dabei werden stichprobenartig Transkripte
      zur Bewertung an OpenRouter (USA) übermittelt — gleiche Verarbeitungsgrundlage wie
      der Live-Chat (§3). Start erst nach DSB-Sign-off (Teil der offenen
      US-Verarbeitungsentscheidung)
- [ ] Prüfung und Sign-off durch Datenschutzbeauftragte:n
