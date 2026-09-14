# Pilot August 2026 — Befunde, Reproduktion, Fixes

**Stand:** 2026-09-14. **Branch:** `fix/pilot-feedback-fixes`.

Dieses Dokument hält fest, welche Fehler in der Testphase (ES-Marketing-Team,
06.–25.08.2026) aufgetreten sind, wo sie in den automatischen Reports und
Transkripten stehen, wie sie reproduziert wurden und was dagegen getan wurde.

## 1. Datenquellen

| Quelle | Ort | Umfang |
|---|---|---|
| Wochenreports (automatisch, `usage-report.yml`) | `docs/usage-reports/2026-W33.md` … `2026-W36.md` | Aggregate pro Woche |
| Feedback-Umfrage (MS Forms) | `docs/usage-reports/Feedback Emba Chatbot – Pilot August 2026.xlsx` (nicht im Repo) | 15 Antworten, 14 auswertbar |
| Pseudonymisierte Transkripte | Prod-Host `/opt/hsg-rag/logs/transcripts/` (verlassen den Host nur zur Auswertung) | 35 Sessions, 169 Turns |
| Usage-Events | Prod-Host `/opt/hsg-rag/logs/usage/` | pro Turn: Outcome, Flags, Timing |

Die Umfrage-Zeitstempel (lokal, UTC+2) wurden auf die Session-Startzeiten
(UTC) abgebildet; Sprache und Programmfokus aus der Umfrage bestätigen die
Zuordnung. 12 von 14 Feedback-Einträgen ließen sich einer Session zuordnen.

## 2. Was die Reports gemeldet haben — und was dahinter steckt

Die Reports sind für das, was sie zählen, exakt: W34 meldet 5 Finanz-Redirects,
1 Aggressiv-Redirect, 4 Max-Turns-Abbrüche und 12 Turns über 15 s. Alle
Zahlen finden sich 1:1 in den Transkripten wieder.

### 2.1 `2026-W34.md` §3 „Scope redirects: 6 (financial_planning: 5, aggressive: 1)“

**Transkript-Befund.** Fünf der Finanz-Redirects stammen aus einer einzigen
Session (11.08., EN): Die Testperson fragte nach dem Darlehensprogramm und
einem Link zur Finanzierungsseite und bekam fünfmal denselben Standardsatz
(„Our admissions team can provide detailed guidance …“), obwohl Turn 1
derselben Session die Darlehensfakten korrekt aus dem Retrieval geliefert
hatte. Der sechste Redirect (25.08., DE) blockierte „ich habe ein budget von
40'000“. Der Aggressiv-Redirect traf „i wont book if i dont know the fee,
worst then imd!!“ — Frust, kein Angriff. Feedback-Eintrag 8 („endless loops
… would harm credibility“) gehört zu dieser Session.

**Reproduktion.** `ScopeGuardian.check_scope()` auf die exakten Nachrichten:
6/6 `financial_planning`, 1/1 `aggressive`. Auslöser: die Keyword-Liste
enthielt `loan`, `financing options`, `budget`, `credit`, `darlehen`,
`finanzierung`; die Aggressiv-Liste `worst`, `terrible`.

**Ursache.** Der Regex-Guard in `src/rag/scope_guardian.py` läuft vor dem
LLM und ersetzt die Antwort komplett. Programmfinanzierung ist aber ein
Programmfakt (emba.unisg.ch/bewerbung/finanzierung-zuschuesse liegt im Index).

**Fix.** `FINANCIAL_KEYWORDS` auf echte Privatfinanz-Begriffe reduziert
(payment plan, mortgage, savings plan, …); `worst`/`terrible` aus
`AGGRESSIVE_KEYWORDS` entfernt. Tests:
`tests/test_pilot_feedback_fixes.py::test_programme_financing_questions_are_on_topic`,
`::test_frustrated_comparison_is_not_aggressive`.

### 2.2 `2026-W34.md` §3 „Max-turns endings: 4“

**Transkript-Befund.** Vier Sessions endeten bei Turn 11 mit der
Maximallängen-Meldung, zwei davon genau bei der Nachfrage, die die Testperson
klären wollte („Warum steht aber auf der Webseite, ich kann mich noch
bewerben?“, „Wo kann ich die Programme herunterladen?“). Feedback 3 nennt die
Meldung explizit als unpassend bei drei Programmen. In einer Session waren 5
der 10 Turns durch Redirects verbraucht.

**Reproduktion.** `config.py`: `MAX_CONVERSATION_TURNS = 20` = 10 Fragen.

**Fix.** Auf 40 erhöht (20 Fragen). `MAX_HISTORY_MESSAGES = 16` deckelt den
LLM-Kontext unabhängig davon, es entstehen keine Mehrkosten pro Turn. Test:
`::test_conversation_allows_at_least_twenty_user_questions`.

### 2.3 `2026-W34.md` §3/§4 „Turns slower than 15 s: 12“, „First token p90 6.6 s“

**Befund.** 14 Turns über 15 s im gesamten Pilot (max. 39,9 s, Time-to-first-
token max. 33,2 s). Feedback 3: „Die Antworten haben zu lange gedauert.“

**Ursachensuche (Usage-Events).**

| Schnitt | n | ftt p50 | ftt p90 |
|---|---|---|---|
| ohne Retrieval-Aufruf | 99 | 1,2 s | 2,9 s |
| mit Retrieval-Aufruf | 43 | 5,0 s | 11,9 s |

11 der 14 langsamen Turns liefen ohne andere aktive Session (±3 min), die
Parallelität (PR #85, 40 Slots) ist also nicht die Ursache. Treiber ist der
Retrieval-Pfad (Tool-Call → Weaviate → zweiter LLM-Aufruf); drei Ausreißer
ohne Retrieval (bis 8,7 s ftt) sind Provider-Latenz.

**Nebenbefund mit Fix.** Die Consent-/Testseiten des Chatbots selbst
(`emba.unisg.ch/chatbot-test`, `/chatbot-test-consent`, DE und EN) waren im
Index, mit allen drei Programmen getaggt, und erschienen in fast jedem
Retrieval-Ergebnis als Rauschen. Fix: `chatbot` in
`src/const/page_blacklist.py`; wirksam nach dem nächsten Scrape + Import.
Test: `::test_chatbot_pages_are_blacklisted`.

**Kein Fix in diesem PR:** die Retrieval-Latenz selbst (bekanntes Thema, siehe
`hsg-rag-failure-archaeology`).

### 2.4 `2026-W34.md` §2 Rubrik-Flags „unresolved_user_need: 4, rude_tone: 1, missed_booking_opportunity: 1“

Im Report nicht auf Sessions zurückführbar. Die Host-Datei
`rubric_scores.json` enthält zwar pro bewerteter Session die Flags, aber
weder den Turn noch den Grund — eine Triage bleibt Raten. Die vier
`unresolved_user_need` decken sich plausibel mit der Finanz-Schleife (2.1),
den Max-Turns-Abbrüchen (2.2) und den Sprachfehlern (3.1); `rude_tone` ist
mit hoher Wahrscheinlichkeit die Aggressiv-Ermahnung aus 2.1.

**Fix.** `scripts/rubric_judge.py` verlangt vom Judge pro Flag jetzt
`flag_evidence` (Turn-Nummer + Grund ≤ 20 Wörter) und speichert sie in der
Host-Datei; der Markdown-Report bleibt anonym. Test:
`::test_rubric_judge_keeps_flag_evidence`.

## 3. Was die Reports NICHT gemeldet haben

### 3.1 Sprachmix-Fehlalarm (7 Turns, 6 Sessions) und Fallback-Ablehnung (9 Turns, 5 Sessions)

**Befund.** Sieben rein englische Nachrichten („i am 26 years old, work in
pharma …“, „How do I know if I am eligble?“) wurden mit „Your message mixes
multiple languages“ abgewiesen; Feedback 9, 11, 12 stammen aus diesen
Sessions, zwei Tester widersprachen im Chat („my earlier message is in
english only“). Neun Kurzeingaben („guten Tag“, „test“, „hii“, „halooo“)
bekamen „I can only reply in English or German“.

**Warum unsichtbar.** `scripts/usage_report.py` zählte die Outcomes
`language_clarification` und `language_fallback` nicht. 16 Fehl-Turns fehlten
in allen Reports.

**Reproduktion.** `LanguageDetector.needs_language_clarification()` auf die
sieben Nachrichten: 7/7 `True`. Auslöser jedes Mal das Wort „am“ (deutsches
Stoppwort, aber englisches „I am“). `detect_language()` auf die neun
Kurzeingaben: 9/9 leer → Fallback.

**Fix.**
- `src/rag/language_detection.py`: `am` in `MIXED_LANGUAGE_AMBIGUOUS_TOKENS`;
  `guten`, `morgen`, `abend`, `grüezi`, `servus` in `SHORT_WORDS_DE`; neue
  Methode `is_confidently_unsupported()` (nur Fremdschrift, fremde Diakritika,
  sicheres Fremdsprachen-Profil oder ≥3 Wörter ohne jedes DE/EN-Signal gelten
  als nicht unterstützt).
- `src/rag/agent_chain.py`: unentscheidbare Eingaben behalten die
  Gesprächssprache und gehen an den Agenten, statt abgelehnt zu werden.
- `scripts/usage_report.py`: beide Outcomes werden jetzt in §3 gezählt.
- Tests: `::test_english_messages_with_i_am_are_not_mixed_language`,
  `::test_german_greetings_are_detected_as_german`,
  `::test_undecidable_input_keeps_language_and_reaches_the_agent`,
  `::test_spanish_input_still_gets_the_fallback_message`,
  `::test_usage_report_counts_language_outcomes`.

### 3.2 Widget: „falsche Ansprechperson“, „man sieht nicht, wo man ist“ (Feedback 3, 4)

**Befund.** Das Widget ist nach dem Consent statisch sichtbar und zeigt immer
drei gleich aussehende Buttons. Nach dem Klick auf eine Beraterin ändert sich
am Button nichts; ein zweiter Klick auf dieselbe Beraterin wirkt wie „nichts
passiert“. In 3 von 15 Widget-Turns ließ das Modell zudem
`relevant_programs` leer.

**Fix.** `src/const/data_consent_constants.py`: Buttons per Helfer erzeugt;
der geklickte Button wechselt in den „aktiv“-Stil (weiß mit grünem Rahmen),
die anderen zurück, das Iframe scrollt ins Bild. `src/rag/agent_chain.py`:
leere `relevant_programs` bei gezeigtem Widget werden aus
`suggested_program` gefüllt. `src/apps/chat/app.py`: das Buchungs-Widget ist
jetzt dritter Output des Chat-Handlers; auf einem Buchungs-Turn wird es nur
mit der Beraterin des betroffenen Programms gerendert, vorausgewählt und mit
geöffnetem Kalender (`booking_widget_for()`), bei zwei Programmen mit beiden,
ohne Programm weiterhin mit allen drei. Informationsturns lassen es
unverändert. Tests: `::test_booking_widget_buttons_mark_the_selected_advisor`,
`::test_booking_widget_for_single_programme_preselects_the_advisor`,
`::test_chat_handler_updates_widget_only_on_booking_turns`. Verifiziert per
Unit-Test und Gradio-Build; ein Klicktest im Browser stand in dieser Session
nicht zur Verfügung und sollte vor dem Merge auf der Testseite gemacht
werden.

### 3.3 Erfundene oder tote Links, „unable to provide download links“ (Feedback 2)

**Befund.** Der Bot gab `https://iemba.unisg.ch/` (existiert nicht) und
`https://emba-x.ch/` (existiert nicht, richtig: `embax.ch`) aus und sagte
dreimal, er könne keine Download-Links liefern. Im Index gibt es keinen Chunk
mit den Programm-Websites.

**Reproduktion.** Replay gegen die echte Chain, je 3 Wiederholungen:
`iemba.unisg.ch` 3/3, „unable to provide“ 3/3. Nicht einmalig.

**Fix.** `src/rag/prompts.py`: Block `OFFICIAL LINKS` mit den geprüften
URLs (Programmseiten, embax.ch, Download-/Broschürenseite, Zulassungsprozess,
Finanzierungsseite, Fristen, MBA HSG, Open Programmes; alle am 14.09.2026
HTTP 200) und die Regel, nur diese auszugeben. Test:
`::test_lead_prompt_lists_official_links_only`.

### 3.4 „I was developed by OpenAI“; erfundene Klassengrößen; harte Nein-Antworten

**Befund.** Identität: 3/3 im Replay. Klassengrößen „erfahrungsgemäß 40 bis
60“: im Pilot einmal, im Replay 2/3, der Korpus enthält dazu nichts (nur die
28 der ersten emba X Kohorte ist belegt). IEMBA „Kann ich mich noch bewerben?“
→ „Nein“, obwohl die Website noch Plätze auswies (Feedback 3). „Ohne
Hochschulabschluss“ → „nicht möglich“ (10./11.08.), obwohl die
Zulassungsseite Sur-Dossier-Zulassung nennt; im Replay am 14.09. antwortet
der Bot 3/3 korrekt, der Chunk liegt inzwischen im Index (wöchentlicher
Scrape). Fit-Frage mit leerem Profil („welches programm passt zu mir?“) →
Dreier-Übersicht statt Rückfragen (Feedback 5, 14).

**Fix.** `src/rag/prompts.py`: Identitätsregel ohne Anbieternennung; keine
„erfahrungsgemäß“-Zahlen; bei geschlossener Frist auf den Advisor verweisen
statt hartes Nein; bei fehlendem Abschluss Sur-Dossier + Open Programmes
nennen; bei dünnem Profil zuerst 2–3 Rückfragen. Test:
`::test_lead_prompt_contains_pilot_conduct_rules`. LLM-Verifikation: siehe §5.

### 3.5 Preisfrage bei geschlossener Bewerbung → Turn-down (Session 11.08. abends, W34 „aggressive: 1“)

**Befund.** Auf „whats the price?“ nannte der Bot für EMBA HSG und IEMBA HSG
keine Gebühr („applications closed, no tuition fee currently available for
booking“), nur für emba X. Die Testperson reagierte mit „i wont book if i
dont know the fee, worst then imd!!“ und bekam dafür die Aggressiv-Ermahnung
(2.1). Gemeint war die Studiengebühr, nicht das kostenlose Beratungsgespräch.

**Ursache.** Zwei Stellen erzwangen den Turn-down: der Facts-Block
(`src/rag/verified_facts.py`, Label `closed`: „Keine Gebühr als aktuell
verfügbar nennen“) und die GENERAL-Regel im Lead-Prompt („never quote its
fees as currently bookable“). Beides diente dem Schutz vor veralteten Preisen,
verhinderte aber jede Preisauskunft.

**Fix.** Beide Stellen umformuliert: Gebühr der Kohorte als Referenzwert
nennen, Bewerbungsfenster (erste bis finale Frist) mit Daten als geschlossen
benennen, sagen, wann man sich wieder bewerben kann (nächste Kohorte, sonst
Ansprechperson gibt das nächste Fenster bekannt). Replay 2026-09-14, je 2×
EN/DE, inklusive der Original-Nachricht aus dem Pilot: 6/6 mit Gebühr,
Fenster-Daten und Hinweis auf das nächste Fenster; die Original-Nachricht
löst keinen Redirect mehr aus. Fact Eval 34/34.

**Grenze.** Die Facts-Pipeline kennt keine Daten der *nächsten* Kohorte; bis
die Website sie publiziert, verweist der Bot auf die Ansprechperson.

### 3.6 „Zu wenig interaktiv, Suchmaschinen-Charakter“ (Feedback 5, 14)

**Befund.** Der Bot begrüßt und wartet; Tester mussten selbst „Stelle mir
Fragen“ schreiben. Feedback 5 wünscht sich eine Einstiegsfrage nach dem
beruflichen Ziel.

**Fix.** `src/const/agent_response_constants.py`: jede Begrüßung (DE/EN)
endet mit einer Einstiegsfrage nach dem beruflichen Veränderungswunsch und
der bevorzugten Studiensprache. Zusammen mit den Rückfragen bei Fit-Fragen
(3.4) startet das Gespräch vom Ziel der Person aus. Test:
`::test_every_greeting_ends_with_the_opening_question`.

## 4. Offen: was aus dem Feedback nicht oder noch nicht umgesetzt ist

### 4.1 Bewusst nicht umgesetzt — Backlog für die Übergabe

Vorgabe für den Pilot: keine neuen Features, Wünsche werden nur dokumentiert.

| Feedback | Wunsch | Stand |
|---|---|---|
| 5 | Bot-Identität: Name, Avatar/Illustration, Rollenbeschreibung, konsistente Persönlichkeit | Der Bot benennt jetzt korrekt, was er ist (§3.4); Name und Avatar fehlen |
| 14 | Kenntnis anderer HSG-Programme (MBA HSG Business Engineering, Executive Master in Management & Law) | Nicht im Index; der Bot kann nur auf mba.unisg.ch und op.unisg.ch verlinken, Vergleiche bleiben vage |
| 2 | Broschüre direkt im Chat herunterladen | Link auf die Download-Seite (§3.3), kein Datei-Download im Chat |
| 2 | Weniger Neutralität gegenüber IMD | Positionierungsentscheidung für die Programmleitung; der Prompt verbietet Konkurrenzbewertungen weiterhin |

### 4.2 Bekannt, kein Quick-Fix

| Quelle | Problem | Stand |
|---|---|---|
| Feedback 3, Reports W33/W34 | Latenz: 14 Turns über 15 s, Treiber Retrieval-Pfad (§2.3) | Eigene Untersuchung nötig, siehe `hsg-rag-failure-archaeology` |
| Feedback 12 | Antworten zu lang fürs schmale Iframe-Feld, Scrollen nötig | UI-Thema für `RUNBOOK_UI_ALTERNATIVEN.md`; ein kleineres Wortbudget im Prompt würde die Dreier-Übersichten beschneiden |

### 4.3 Nicht überprüfbar

- Rubrik-Flags in W34 (4 `unresolved_user_need`, 1 `rude_tone`, 1
  `missed_booking_opportunity`): für den Pilot nachträglich nicht mehr auf
  Turns zurückführbar; ab dem nächsten Report liefert der Judge Turn und
  Grund pro Flag (2.4).
- Feedback 13 (17.08., 16:13) hat keine passende Session; Feedback 6 ist leer.

### 4.4 Operativ nach dem Merge

- Scrape und Re-Import auslösen, sonst bleiben die Consent-Seiten im Index
  (§2.3).
- CAS-Anrechnung (Session 10.08., „sind es denn nicht 12 ECTS?“): der Bot
  nennt jetzt keine Zahl mehr; ob es eine Anrechnungsregel gibt, muss die
  Programmleitung EMBA HSG klären. Falls ja, gehört sie auf die Website, dann
  landet sie über den Scrape im Index.

## 5. Verifikation

| Gate | Ergebnis |
|---|---|
| Offline-Suite `pytest -q` | 390 passed, 1 skipped |
| Neue Regressionstests `tests/test_pilot_feedback_fixes.py` | 51 passed |
| LLM Fact Eval (`RUN_LLM_EVAL=1`) | 34/34 passed (2026-09-14, nach jeder Prompt-Änderung wiederholt) |
| Replay der Pilot-Fragen (3× je Fall, echte Chain, 2026-09-14) | 0/24 Defekte, Tabelle unten |

Replay vor und nach dem Fix (Defekt vorhanden, von 3 Wiederholungen):

| Fall (Original-Frage aus dem Pilot) | vorher | nachher |
|---|---|---|
| „how made you?“ → nennt OpenAI | 3/3 | 0/3 |
| „What is the website of iemba?“ → tote URL | 3/3 | 0/3 (emba.unisg.ch/en/programm/iemba) |
| „wie gross sind die Klassen je Programm?“ → erfundene Spanne | 2/3 | 0/3 („wird nicht veröffentlicht“) |
| Broschüren-Link emba X → „unable to provide“ | 3/3 | 0/3 (Download-Seite) |
| ohne Studium → keine Alternative genannt | 3/3 | 0/3 (Sur-Dossier + Open Programmes) |
| Darlehens-Link nach Stipendienfrage → Finanz-Schleife | 5/5 Redirects im Pilot | 0/3 (Finanzierungsseite verlinkt) |
| „welches programm passt zu mir?“ → Übersicht statt Rückfragen | Pilot | 0/3 (drei Rückfragen) |
| IEMBA „Kann ich mich noch bewerben?“ → hartes „Nein“ | Pilot | 0/3 (Frist abgelaufen, Advisor genannt; Kohorte ist inzwischen gestartet) |
