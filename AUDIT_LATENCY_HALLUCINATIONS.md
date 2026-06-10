# Audit: Latency & Halluzinationen — HSG_RAG (`fix/chatbot-overhaul`)

**Datum:** 2026-06-10
**Scope:** RAG-Chatbot zur Beratung für EMBA HSG, IEMBA HSG, emba X (DE/EN) inkl. Termin-Handover.
**Kernbefund:** Latency- und Halluzinationsprobleme haben dieselbe Wurzel — eine überdimensionierte Pipeline mit zu vielen sequenziellen LLM-Calls und ~2000 Zeilen fehleranfälliger Regex-Heuristiken, die das LLM umgehen.

---

## 1. Request-Flow pro User-Turn (Ist-Zustand)

Alle Schritte laufen **sequenziell und blockierend**, kein Streaming:

| # | Schritt | Datei | Kosten |
|---|---------|-------|--------|
| 1 | Input-Normalisierung (Regex) | `src/rag/input_handler.py` | vernachlässigbar |
| 2 | Spracherkennung per **LLM-Call** (gpt-4o-mini) für Inputs >3 Wörter, bis Language-Lock | `src/rag/language_detection.py:108` | ~0.5–1.5 s |
| 3 | ~10 Keyword-Router-Checks (Programme-Facts, Application-Steps, Continuation, Scope …) | `src/rag/agent_chain.py:861–968` | gering, aber fehleranfällig |
| 4 | Lead-Agent-Loop mit **gpt-5.1** (Reasoning-Modell): min. 2 Modellcalls (Tool-Entscheidung → finale Antwort) | `src/config/configs.py:169`, `agent_chain.py:1027` | **10–30 s** |
| 5 | Retrieval: Weaviate Cloud, Hybrid-Query mit **Remote-Vektorisierung via HuggingFace Inference API** | `src/database/weavservice.py:341,448` | 1–5 s, instabil |
| 6 | **Quality-Eval per LLM-Call** (gpt-4o-mini), per Default AN (`ENABLE_EVALUATE_RESPONSE_QUALITY=True`) — nach fertiger Antwort, verwirft sie bei Score < Threshold | `src/rag/quality_score_handler.py`, `agent_chain.py:1066` | 1–3 s |
| 7 | Formatting, Chunking, Booking-Heuristiken | `agent_chain.py:1048–1148` | gering |

**Realistische End-to-End-Latenz: 15–40 s pro Antwort.**

---

## 2. Latency-Ursachen (priorisiert)

### L1 — gpt-5.1 als Hauptmodell *(größter Einzelhebel)*
`src/config/configs.py:169` (`OPENAI_MODEL = "gpt-5.1"`). Ein Reasoning-Modell für einen Beratungs-Chatbot mit eng begrenztem Themenfeld ist Overkill. Der Agent-Loop verdoppelt die Calls (Tool-Call-Runde + Antwort-Runde).

### L2 — Blockierender Quality-Eval-Call im Request-Pfad
`src/rag/quality_score_handler.py` + `agent_chain.py:1066–1074`. Der User wartet auf eine zusätzliche LLM-Bewertung der bereits fertigen Antwort. Bei Score < `CONFIDENCE_THRESHOLD` wird die Antwort verworfen und durch eine Fallback-Message ersetzt — die gesamte Wartezeit war dann umsonst.

### L3 — Kein Streaming
`src/apps/chat/app.py` (`_chat` gibt erst nach kompletter Pipeline zurück). Gradio unterstützt Generator-Funktionen; gefühlte Latenz könnte auf Time-to-first-Token sinken.

### L4 — LLM-Call für Spracherkennung
`src/rag/language_detection.py:108–123`. Pro Turn ein gpt-4o-mini-Call (bis Language-Lock greift), für ein Zwei-Sprachen-Problem, das eine lokale Library (`lingua-py`, `langdetect`) in <10 ms löst.

### L5 — Remote-Embedding über HuggingFace Inference API
`src/database/weavservice.py:448` (`text2vec_huggingface`). Jede Query wird remote vektorisiert. Der eingebaute BM25-Fallback (`weavservice.py:347–360`, `_should_fallback_to_bm25`) existiert nur, weil dieser Pfad regelmäßig fehlschlägt — d. h. zusätzliche Timeouts im Fehlerfall und schlechtere Retrieval-Qualität im Fallback.

### L6 — Unbegrenzt wachsende Conversation-History
`agent_chain.py:1029` schickt `_conversation_history` ungekürzt bei jedem Turn. Der Summarization-Prompt (`prompts.py:180–186`) wird **nirgends verwendet**. Turns werden progressiv langsamer und teurer.

### L7 — Retry-/Fallback-Multiplikation im Worst Case
`MAX_RETRIES=3` (Middleware, `middleware.py:60`) × `ModelFallbackMiddleware` mit 2–4 Fallback-Modellen (`configs.py:181–200`) × Weaviate-Retries (`weavservice.py:320`). Ein hängender Provider kann Minuten kosten.

### L8 — Subagent-Architektur (default aus, aber im Code)
`src/rag/subagents.py` + `agent_chain.py:151–212`: Lead-Agent → Subagent (eigener Agent-Loop, gpt-5-mini) → Retrieval → zurück. Verdoppelt LLM-Calls. Der Code warnt selbst: *"This might lead to high response times!"* (`agent_chain.py:217`).

### L9 — Cache praktisch wirkungslos
`CACHE_ENABLED` default `False` (`configs.py:89`); Key ist die exakte Query pro Session (`agent_chain.py:972`) — Hit-Rate nahe null.

---

## 3. Halluzinations-Ursachen (priorisiert)

### H1 — Regex-"Fact-Extraction" ordnet Fakten falschen Programmen zu *(gefährlichste Quelle)*
`agent_chain.py:1441–2455` (~1000 Zeilen): CHF-Beträge, Daten, Dauern werden per Regex aus Retrieval-Chunks gezogen (`_extract_chf_amounts:2207`, `_extract_future_dates:2248`, `_extract_duration_values:2283`) und Sätze per Keyword-Matching einem Programm zugeordnet (`_sentence_matches_programme:1994`). Erwähnt ein Chunk EMBA- **und** IEMBA-Preise, kann der falsche Betrag dem falschen Programm zugeordnet werden. Diese deterministischen Pfade **umgehen das LLM komplett** — was wie eine Modell-Halluzination aussieht, ist hier ein Code-Bug. Vorgeschichte im Git-Log („Fix IEMBA pricing and prevent cross-programme price aggregation") zeigt: genau dieses Problem trat bereits auf und wurde mit *noch mehr* Heuristiken gepatcht.

### H2 — Zu wenig Kontext fürs LLM
`TOP_K_RETRIEVAL=4` (`configs.py:82`) × `CHUNK_MAX_TOKENS=200` (per Commit von 8191 reduziert) ≈ **800 Tokens Kontext**. Bei dünnem/leerem Ergebnis füllt das Modell Lücken aus Weltwissen. Es gibt **keinen Leer-Kontext-Check** vor der Antwortgenerierung (`agent_chain.py:113–135` liefert bei 0 Treffern einfach einen Leerstring als Tool-Ergebnis).

### H3 — BM25-Fallback senkt Retrieval-Qualität still
`weavservice.py:347–360`: Schlägt die HF-Vektorisierung fehl, wird stillschweigend auf reines Keyword-Matching degradiert — schlechtere Treffer → mehr Lückenfüllen durch das Modell. Kein Flag in der Antwort, kein Monitoring.

### H4 — Quality-Gate kann Halluzinationen prinzipiell nicht erkennen
`prompts.py:196–198`: Der Scoring-Prompt bewertet „format, context, pricing, scope, rules", bekommt aber **den Retrieval-Kontext nicht zu sehen**. Ein Grounding-/Faithfulness-Check ist so unmöglich. Der Call kostet nur Zeit (siehe L2).

### H5 — Keyword-Router liefern Template-Antworten auf falsch klassifizierte Fragen
Hunderte hartkodierte Begriffe (`_is_explicit_booking_intent:541`, `_is_programme_fact_request:1441`, `_is_booking_preference_follow_up:406` u. v. m.) routen Queries an vorgefertigte Antwortpfade, bevor das LLM die Frage sieht. False Positives ⇒ Antworten, die an der Frage vorbeigehen.

### H6 — Marketing-Positioning im Prompt als Fakten-Restquelle
`prompts.py:58–96`: Die `program_specifics` enthalten faktennahe Aussagen. Der Prompt versucht das einzuhegen („CURRENT FACTS … must come from retrieve_context()"), aber bei leerem Retrieval bleibt das Positioning die einzige „Quelle" — und das Modell nutzt sie.

---

## 4. Empfohlene Ziel-Architektur

Für 3 Programme / 2 Sprachen / Termin-Handover reicht **ein LLM-Call pro Turn**:

```
User-Input
  → lokale Spracherkennung (lingua-py, <10 ms)
  → EIN Agent (schnelles Non-Reasoning-Modell, z. B. gpt-4.1 / gpt-5-mini)
      System-Prompt enthält: kuratierte Programm-Fakten (YAML/JSON, ~500 Tokens)
      Tools: retrieve_context (nur Long-Tail-Fragen), Structured Output für Booking-Flags
  → Streaming an die UI
```

**Kernidee:** Preise, Deadlines, Dauer, Format der 3 Programme ändern sich selten. Eine gepflegte `programme_facts.yaml` direkt im Kontext eliminiert (a) die komplette Regex-Extraktion (~2000 Zeilen), (b) die Hauptquelle falscher Zahlen und (c) die meisten Retrieval-Roundtrips. RAG bleibt für Curriculum-Details, Zulassungsfragen etc.

**Erwarteter Effekt:** `agent_chain.py` 3200 → ~300–400 Zeilen; Antwortzeit 15–40 s → 2–5 s (gefühlt <1 s mit Streaming); Halluzinationsquellen H1, H5, H6 vollständig eliminiert.

---

## 5. To-do-Liste (priorisiert)

### Phase 1 — Quick Wins (Stunden, kein Architektur-Umbau)
- [ ] **1.1** Hauptmodell tauschen: `configs.py:169` `OPENAI_MODEL` → `gpt-4.1` o. ä. (1 Zeile, größter Hebel)
- [ ] **1.2** Quality-Eval deaktivieren: `ENABLE_EVALUATE_RESPONSE_QUALITY=False` (env/`config.py`) — später optional async/offline via LangSmith
- [ ] **1.3** Spracherkennung lokal: LLM-Call in `language_detection.py:detect_language` durch `lingua-py` ersetzen
- [ ] **1.4** Streaming: `_chat` in `src/apps/chat/app.py` als Generator + `agent.stream()` statt `invoke()`
- [ ] **1.5** Retries begrenzen: `MODEL_MAX_RETRIES` 3 → 2, Fallback-Kette auf 1 Modell kürzen
- [ ] **1.6** `TOP_K_RETRIEVAL` 4 → 8 (kompensiert die 200-Token-Chunks bis zum Re-Chunking)

### Phase 2 — Halluzinationen strukturell beheben (Tage)
- [ ] **2.1** `programme_facts.yaml` erstellen (Preise, Deadlines, Dauer, Format, Sprache, Advisor je Programm; DE/EN) und in den System-Prompt injizieren
- [ ] **2.2** Regex-Fact-Extraction entfernen: `agent_chain.py:1441–2455` + zugehörige Router löschen; Fact-Fragen beantwortet das LLM aus 2.1
- [ ] **2.3** Leer-Kontext-Guard: Wenn `retrieve_context` 0 Treffer liefert → explizite Tool-Message „Keine Daten gefunden — sage das dem User", statt Leerstring
- [ ] **2.4** BM25-Fallback sichtbar machen (Log-Alert/Metrik) oder Embedding-Provider wechseln (2.6)
- [ ] **2.5** Keyword-Router (`_is_*`-Methoden) auf das Minimum reduzieren: nur Scope-Check + explizites Booking; Rest dem LLM überlassen
- [ ] **2.6** Embeddings weg von der HF-Inference-API: OpenAI `text-embedding-3-small` oder lokales Modell; Chunks neu mit 512–1024 Tokens einbetten

### Phase 3 — Verschlanken & stabilisieren (Tage)
- [ ] **3.1** Subagents komplett entfernen (`subagents.py`, `_call_*_agent`, `ENABLE_SUBAGENTS`-Pfade)
- [ ] **3.2** History-Management: nach ~10 Turns zusammenfassen (Summarization-Prompt existiert bereits in `prompts.py:180`)
- [ ] **3.3** Booking-Heuristiken (`_previous_response_*`, `_is_booking_preference_follow_up` …) durch Structured-Output-Flags des Agents ersetzen
- [ ] **3.4** Toten Code löschen: ungenutzter Summarization-Pfad, `dbapp`-Reste, doppelte `utilclasses.py`, ChromaDB-Artefakte (`data/vectordb/chroma.sqlite3`)
- [ ] **3.5** Latenz-Monitoring: Timing-Logs pro Pipeline-Schritt (Spracherkennung, Retrieval, LLM, Formatting), damit Regressionen sofort auffallen
- [ ] **3.6** Eval-Set aufbauen: ~30 Fakten-Fragen (DE/EN) mit Soll-Antworten aus `programme_facts.yaml`, als Regressionstest vor jedem Release
