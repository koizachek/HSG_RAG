# Chatbot-Overhaul: Diagnose, Maßnahmen, Ergebnis

**Zeitraum:** 2026-06-10 / 2026-06-11 · **Branch:** `master`
**Scope:** RAG-Chatbot zur Beratung für EMBA HSG, IEMBA HSG, emba X (DE/EN) inkl. Termin-Handover.

## Ergebnis (vorher → nachher)

| Metrik | Vorher | Nachher |
|---|---|---|
| Antwortzeit (end-to-end) | 15–40 s | **~6 s** (gemessen: 31 Eval-Turns in 181 s) |
| Gefühlte Latenz | 15–40 s | **<1 s** (Token-Streaming) |
| LLM-Calls pro Turn | 3–6 (Sprachdetect + Agent-Loop + Quality-Eval) | **1 Agent-Loop** (Sprache lokal, kein Eval-Call) |
| Falsche Programm-Preise | wiederkehrend (siehe Git-Historie) | **0 in 31 Eval-Fällen** inkl. Kontaminations-Checks |
| `agent_chain.py` | 3'200 Zeilen | **~1'200 Zeilen** |
| Fakten-Aktualität | manuell / Regex aus Chunks geraten | **auto-generiert aus offiziellen Quellen**, Cron + Diff-Alerts |
| Regressionsschutz | keiner | **31 LLM-Eval-Fälle + Offline-Unit-Tests** |

---

## 1. Diagnose (Ausgangszustand)

### Latency
1. **gpt-5.1 (Reasoning) als Hauptmodell** — 10–30 s pro Agent-Loop.
2. **Blockierender Quality-Eval-LLM-Call** nach jeder fertigen Antwort (verwarf sie bei niedrigem Score).
3. **Kein Streaming** — Gradio erhielt die Antwort erst nach der kompletten Pipeline.
4. **LLM-Call zur Spracherkennung** pro Turn (gpt-4o-mini, bis Language-Lock).
5. **Remote-Vektorisierung** über HuggingFace Inference API (instabil; stiller BM25-Fallback).
6. **Unbegrenzt wachsende History** pro Turn mitgeschickt; Summarization-Prompt existierte, wurde nie benutzt.
7. **Retry-Multiplikation:** 60-s-Timeouts × 3 Retries × 2–4 Fallback-Modelle.
8. Subagent-Architektur (Lead → Subagent → Retrieval) hätte Calls verdoppelt (war default aus).

### Halluzinationen
1. **Regex-Fakten-Extraktion (~2'000 Zeilen):** CHF-Beträge/Daten/Dauern wurden per Regex aus Chunks gezogen und per Keyword-Matching Programmen zugeordnet — konnte Preise dem falschen Programm zuschreiben. Deterministischer Code-Bug, der wie eine LLM-Halluzination aussah.
2. **Zu wenig Grounding:** 4 Chunks × 200 Tokens ≈ 800 Tokens Kontext; kein Leer-Kontext-Check → Modell füllte Lücken aus Weltwissen.
3. **Quality-Gate ohne Grounding:** Der Scoring-Prompt sah den Retrieval-Kontext nie — konnte Halluzinationen prinzipiell nicht erkennen.
4. **Keyword-Router** beantworteten falsch klassifizierte Fragen mit Template-Antworten.
5. Chunks ohne Quellen-/Programm-Metadaten — anonymer Textblock fürs Modell.

---

## 2. Maßnahmen (alle umgesetzt)

### Latency
- [x] Hauptmodell gpt-5.1 → **gpt-4.1** (`config.py`)
- [x] Quality-Eval aus dem Request-Pfad entfernt
- [x] **Spracherkennung lokal** (Stopwort-Heuristik + Umlaute + Skript-Erkennung; LLM nur noch als Fallback bei echter Ambiguität, lazy initialisiert) — `src/rag/language_detection.py`
- [x] **Token-Streaming**: inkrementeller JSON-Feld-Parser (`src/rag/stream_parser.py`, extrahiert live das `response`-Feld aus dem Structured-Output-Stream), `on_delta`-Callback durch die Chain, Gradio-Generator mit Worker-Thread; automatischer Fallback auf blocking `invoke`
- [x] History-Cap (`MAX_HISTORY_MESSAGES=16`), Timeouts 60→30 s/10 s, Retries 3→2, Fallback-Kette auf 1 Modell
- [x] **Timing-Logs** pro Pipeline-Schritt (`[timing] preprocessing / agent loop / total turn`)

### Halluzinationen
- [x] **Verifizierte Faktenbasis** `data/database/programme_facts.json`: Preise, Fristen, Starts, Dauer, Struktur, Orte, Advisors für alle 3 Programme — gegen die offiziellen Quellen geprüft (emba.unisg.ch, emba.unisg.ch/bewerbung/fristen, embax.ch)
- [x] **Prompt-Injection** des Faktenblocks (DE/EN) als autoritative Quelle für volatile Fakten (`src/rag/verified_facts.py`), inkl. Regel für abgelaufene Fristen
- [x] **Auto-Regeneration**: `src/pipeline/update_programme_facts.py` scrapt die Quellseiten, extrahiert per Structured Output, difft gegen den Bestand, alarmiert via Notification-Center (E-Mail/Slack) bei Preis-/Fristen-Änderungen. **Cron: täglich 06:00.** Niemand pflegt das File von Hand.
- [x] Leer-Kontext-Guard im Retrieval (explizites `NO_CONTEXT_FOUND` statt Leerstring)
- [x] Retrieval-Chunks mit `[programme | source]`-Metadaten-Header
- [x] TOP_K 4→8

### Verschlankung (netto >6'000 Zeilen entfernt)
- [x] **Regex-Fakten-Router komplett gelöscht** (~1'800 Zeilen in `agent_chain.py`; anker-basiertes Lösch-Skript mit Compile-Check)
- [x] **Subagents gelöscht** (`subagents.py`, Call-Wrapper, Config, Prompt-Routing, Modell) — Single-Agent-Hot-Path; Multi-Agent nur noch offline (Fakten-Extraktions-Agent)
- [x] Alter chunk-basierter `ProgrammeFactsProvider` gelöscht
- [x] 4 Legacy-Test-Suiten gelöscht (testeten gelöschtes Verhalten)

### Tests
- [x] `tests/test_verified_facts.py` — offline: Faktenbasis-Invarianten (Gebühren eindeutig pro Programm, Frühbucher < Final), Prompt-Rendering, Sprach-Heuristik, Config
- [x] `tests/test_stream_parser.py` — offline: Stream-Parser inkl. Fuzz über Chunk-Grenzen, Escapes, Unicode
- [x] `tests/test_llm_fact_eval.py` — **31 LLM-Eval-Fälle (DE/EN)**, Soll-Werte dynamisch aus `programme_facts.json`; Kern: Kontaminations-Guards (EMBA-Preisfrage darf keine IEMBA/emba-X-Preise enthalten), Honesty-Checks, Ambiguitäts-Verhalten. Opt-in: `RUN_LLM_EVAL=1 pytest tests/test_llm_fact_eval.py`
- **Stand 2026-06-11: 31/31 passed.**

---

## 3. Ziel-Architektur (Ist-Zustand)

```
User-Input
  → lokale Spracherkennung (<1 ms; LLM-Fallback nur bei Ambiguität)
  → Scope-Check (Keyword, lokal)
  → EIN Lead-Agent (gpt-4.1, Structured Output)
      System-Prompt: Persona + Regeln + VERIFIED PROGRAMME FACTS (auto-generiert)
      Tool: retrieve_context (Weaviate hybrid, nur für Long-Tail-Fragen)
  → Token-Streaming an Gradio (Booking-Flags am Stream-Ende)

Offline (kein User wartet):
  Scraping-Pipeline → Fakten-Extraktions-Agent → programme_facts.json
  → Diff-Alert bei Änderungen (E-Mail/Slack) → Cron täglich 06:00
```

## 4. Offene Punkte (bewusst nicht gemacht)

- **Embeddings:** Die Migration auf app-seitig erzeugte OpenRouter-Embeddings (`openai/text-embedding-3-small`) erfordert weiterhin Neu-Erstellung der Weaviate-Collection + Re-Import. Der BM25-Fallback loggt sichtbar, falls Embedding oder Vektor-Hybrid-Query fehlschlägt.
- **Merge-Strategie:** lokale Arbeit liegt auf `master`, Remote-Hauptbranch ist `main` — vor dem Push klären (Rename oder PR).
- Cron läuft auf dem Entwicklungs-Mac nur, wenn er wach ist — auf dem Produktivserver einrichten.
- `scripts/remove_legacy_code.py` ist ein verbrauchtes Einweg-Skript und kann gelöscht werden.

## 5. Betrieb

```bash
# Tests
pytest tests/test_verified_facts.py tests/test_stream_parser.py -v   # offline, sekundenschnell
RUN_LLM_EVAL=1 pytest tests/test_llm_fact_eval.py -v                 # vor jedem Release (~3 min)

# Fakten manuell aktualisieren (z. B. bei neuen Fristen)
python -m src.pipeline.update_programme_facts --dry-run   # nur Diff anzeigen
python -m src.pipeline.update_programme_facts             # anwenden + ggf. Alert

# Latenz beobachten
grep "\[timing\]" logs/rag_chatbot.log
```
