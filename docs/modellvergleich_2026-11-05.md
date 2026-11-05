# Modellvergleich Haupt-Agent — Auswertung vom 2026-11-05

**Stand:** 2026-11-05. **Produktion:** unverändert `openai/gpt-4.1`. **Anlass:** Laut
Drittquellen nimmt OpenAI `gpt-4.1` und `gpt-4o-mini` am 2027-01-14 aus der eigenen
API (offizielle Seite nicht direkt geprüft; Termin auf OpenRouter offen).

**Entscheidung (freigegeben 2026-11-05):** `google/gemini-3.5-flash-lite`
als Haupt-Agent, `openai/gpt-5.6-luna` als Fallback. Umsetzung und Gates: Abschnitt 11.

## 1. Ergebnis im Überblick

Preise von OpenRouter pro 1 Mio. Tokens (Input/Output). UAT mit `openai/gpt-4.1` als
Judge. Median und Mittelwert: Antworten mit Modellaufruf (über 0,5 s).

| Modell (Effort) | Preis | UAT-Schnitt | Schlechtester Fall | Median | Mittelwert | Fact-Eval | Status |
|---|---|---|---|---|---|---|---|
| `gpt-4.1` (aktuell) | $2 / $8 | 9,09 | 8,0 | 3,44 s | 5,74 s | 34/34 | Referenz |
| `gemini-3.5-flash-lite` (low) | $0,30 / $2,50 | 9,14 | 8,5 | 3,54 s | 3,94 s | 34/34 | **empfohlen** |
| `gpt-5.6-luna` (low) | $0,20 / $1,20 | 9,27 | 8,0 | 6,87 s | 6,06 s | 34/34 | Alternative, 1 falscher Wert in der Pipeline |
| `gemini-3.8-flash` (low) | $0,825 / $4,125 | 9,41 | 8,0 | 7,80 s | 8,31 s | nicht gelaufen | bestanden, langsam, teuer |
| `claude-haiku-5.5` (low) | $0,10 / $0,50 | 9,14 | 7,5 | 3,11 s | 4,59 s | nicht gelaufen | verworfen |
| `gpt-6-luna` (low) | $0,10 / $0,50 | 9,23 / 9,00 | 7,5 | 5,38–5,83 s | 5,30–6,66 s | 34/34 | verworfen |
| `gpt-6-luna` (Standard) | $0,10 / $0,50 | 9,14 | 8,5 | 8,63 s | 10,04 s | nicht gelaufen | verworfen, zu langsam |
| `gpt-6.1-terra` (low) | $1 / $5 | 9,14 | 8,0 | 6,78 s | 6,70 s | nicht gelaufen | vom Maintainer gestrichen (Kosten) |
| `mistral-large-4-0` (low) | $0,70 / $2,10 | – | – | – | – | nicht gelaufen | abgebrochen, 1 von 11 Fällen |
| `mistral-medium-3-5` (low) | $1,50 / $7,50 | – | – | – | – | nicht gelaufen | abgebrochen, 1 von 11 Fällen |
| `claude-sonnet-5.5` (low) | $2 / $10 | – | – | – | – | nicht gelaufen | auf Wunsch abgebrochen, kein Ergebnis |

## 2. Methode

- **UAT:** `tests/test_uat_llm_judge.py`, 11 Fälle. Gate: Schnitt mindestens 8,5, jeder
  Fall mindestens 8,0. Judge wie in der CI `openai/gpt-4.1`.
- **Fact-Eval:** `tests/test_llm_fact_eval.py`, 34 Fälle, eine Wiederholung pro Fall bei
  einem Fehlschlag. Ob Wiederholungen nötig waren, wurde nicht ausgewertet.
- **Wiederholungen:** kritische Fälle TC-EDGE-01 und TC-IEMBA-01 (teils TC-EDGE-03).
- **Fakten-Pipeline:** `src.pipeline.update_programme_facts --dry-run`, Ergebnis gegen
  `data/database/programme_facts.json` verglichen. Es wurde nichts geschrieben.
- **Durchführung:** Der Haupt-Agent wurde per Override außerhalb des Repos gesetzt,
  Testcode und `main` blieben unverändert. Nur der Haupt-Agent wurde gewechselt.
- **Nachweis des Modells:** Bei den Vergleichsläufen ab Terra wurde das antwortende
  Modell erfasst. Terra, Haiku, Gemini 3.8, `gpt-5.6-luna` und Flash Lite: nur das
  getestete Modell, kein Fallback. Bei den ersten vollen UAT-Läufen von `gpt-4.1` und
  `gpt-6-luna` fehlen die Logs, ein Fallback ist dort nicht auszuschließen.

**Einschränkungen:**
- Je Modell meist ein voller UAT-Lauf; Unterschiede von wenigen Zehnteln sind nicht belastbar.
- Läufe liefen parallel und mit wechselnder Last (bis zu 5 gleichzeitig). Zeiten sind
  nur grob vergleichbar. Die Zeiten sind Gesamtzeiten je Antwort, nicht das erste Token.
- Gespeicherte Antworten wurden teils überschrieben, einzelne 7,5-Antworten fehlen daher.
- Rohdaten lagen nur im temporären Sitzungsordner, sie sind nicht im Repo.

## 3. UAT je Fall (Judge `gpt-4.1`)

| Fall | `gpt-4.1` | Luna Std | Luna low (1) | Luna low (2) | Terra | Haiku | Gemini 3.8 | `gpt-5.6-luna` | Flash Lite |
|---|---|---|---|---|---|---|---|---|---|
| TC-EDGE-01 | 8,0 | 9,0 | 10,0 | **7,5** | 9,5 | 9,0 | 9,5 | 9,5 | 9,0 |
| TC-EDGE-02 | 10,0 | 10,0 | 10,0 | 10,0 | 10,0 | 10,0 | 10,0 | 10,0 | 10,0 |
| TC-EDGE-03 | 9,5 | 8,5 | **7,5** | 8,0 | 8,0 | 8,5 | 8,0 | 9,0 | 9,5 |
| TC-EDGE-04 | 9,0 | 9,0 | 9,0 | 9,0 | 9,0 | 9,0 | 9,0 | 8,0 | 9,0 |
| TC-EDGE-05 | 10,0 | 10,0 | 10,0 | 10,0 | 10,0 | 10,0 | 10,0 | 10,0 | 10,0 |
| TC-EMBA-01 | 9,0 | 8,5 | 9,0 | 8,5 | 8,0 | 9,0 | 9,5 | 9,0 | 9,0 |
| TC-EMBA-02 | 9,5 | 9,5 | 9,5 | 9,5 | 9,5 | 9,5 | 9,5 | 9,5 | 8,5 |
| TC-EMBA-03 | 9,0 | 9,0 | 9,0 | 9,0 | 9,5 | 9,5 | 9,5 | 9,5 | 9,0 |
| TC-EMBAX-01 | 9,0 | 9,5 | 9,5 | 9,5 | 9,5 | 9,0 | 9,5 | 9,5 | 8,5 |
| TC-IEMBA-01 | 8,5 | 8,5 | 9,5 | 9,5 | 8,5 | **7,5** | 9,5 | 8,5 | 8,5 |
| TC-IEMBA-02 | 8,5 | 9,0 | 8,5 | 8,5 | 9,0 | 9,5 | 9,5 | 9,5 | 9,5 |
| **Schnitt** | 9,09 | 9,14 | 9,23 | 9,00 | 9,14 | 9,14 | 9,41 | 9,27 | 9,14 |

Luna low (1): per Override. Luna low (2): mit der Konfiguration im Branch.

## 4. Wiederholungen der kritischen Fälle (Judge `gpt-4.1`)

Enthalten sind der erste Lauf und die Wiederholungen.

| Modell | Fall | Scores | Unter 8,0 |
|---|---|---|---|
| `gpt-4.1` | TC-EDGE-01 | 8,0 / 9,0 / 8,0 / 9,0 / 8,5 / 9,5 | 0 von 6 |
| `gpt-6-luna` (low) | TC-EDGE-01 | 10,0 / 7,5 / 9,5 / 8,5 / 9,5 / 6,0 | 2 von 6 |
| `gpt-6-luna` (low) | TC-EDGE-03 | 7,5 / 8,5 / 9,0 / 9,0 | 1 von 4 |
| `gpt-6-luna` (Standard) | TC-EDGE-03 | 8,5 / 8,5 / 8,0 / 8,5 | 0 von 4 |
| `claude-haiku-5.5` | TC-IEMBA-01 | 7,5 / 8,5 / 7,5 / 8,5 / 8,5 / 7,5 / 8,5 / 7,5 / 8,5 / 7,5 / 7,5 | 6 von 11 |
| `claude-haiku-5.5` | TC-EDGE-01 | 9,0 / 9,5 / 9,0 / 9,0 / 10,0 / 9,0 | 0 von 6 |
| `gpt-6.1-terra` | TC-EDGE-01 | 9,5 / 9,0 / 9,0 / 10,0 / 9,0 / 9,0 | 0 von 6 |
| `gemini-3.8-flash` | TC-EDGE-01 | 9,5 / 9,0 / 9,5 / 9,5 / 9,5 / 9,5 | 0 von 6 |
| `gpt-5.6-luna` | TC-EDGE-01 | 9,5 / 9,0 / 9,5 / 9,0 / 9,0 / 8,5 | 0 von 6 |
| `gpt-5.6-luna` | TC-IEMBA-01 | 8,5 / 9,5 / 8,5 / 9,5 / 8,5 / 8,5 | 0 von 6 |
| `gemini-3.5-flash-lite` | TC-EDGE-01 | 9,0 / 9,0 / 9,0 / 9,0 / 9,0 / 9,0 | 0 von 6 |
| `gemini-3.5-flash-lite` | TC-IEMBA-01 | 8,5 / 8,5 / 8,5 / 7,5 / 7,5 / 8,0 | 2 von 6 |

## 5. Befunde je Modell

### `gpt-6-luna` — verworfen
- Antworten faktisch korrekt, aber bei nicht erfüllten Kriterien fehlt oft die
  Alternative (regulärer MBA), obwohl `src/rag/prompts.py` sie verlangt.
- Effort-Vergleich im UAT: kein erkennbarer Qualitätsgewinn von Standard gegenüber
  `low`, aber 8,63 s statt 5,83 s Median.
- **Versuch mit zwei zusätzlichen Prompt-Regeln, zurückgenommen.** Ergebnis: UAT-Schnitt
  8,77, TC-EDGE-01 und TC-IEMBA-02 je 7,5; TC-EDGE-01 in 6 von 10 Wiederholungen unter 8,0
  (10,0 / 7,0 / 7,5 / 6,5 / 7,5 / 10,0 / 7,5 / 9,0 / 7,5 / 9,5). Die Regel zur Ansprechperson
  bei Frustration wirkte (TC-EDGE-03: namentliche Ansprechperson in 10 von 10, 1 von 10
  unter 8,0), die Regel zur Alternative nicht. `src/rag/prompts.py` ist wieder identisch mit `main`.
- In 4 von 10 Antworten auf den „Wucher“-Vorwurf steht CHF 77'500 vor der aktuell
  geltenden Gebühr von CHF 72'500, einmal direkt im ersten Satz. Das ist keine
  Programm-Vermischung, kann aber einen falschen Preis vermitteln.

### `claude-haiku-5.5` — verworfen
TC-IEMBA-01 lag in 6 von 11 Läufen unter 8,0. Im ersten Lauf antwortet es auf die Frage
nach dem Alumni-Netzwerk nur, es rufe die aktuellen Informationen ab. Die Antwort selbst
fehlt. Die Wiederholungen wurden nicht einzeln gelesen.

### Mistral — abgebrochen
Beide Läufe wurden nach 45 Minuten bei je 1 von 11 Fällen gestoppt.

| | `mistral-large-4-0` | `mistral-medium-3-5` |
|---|---|---|
| **TC-EMBA-01, Score** | 8,5 | 7,5 |
| **Antwortzeiten je Zug** | 18 / 863 / 50 / 907 / 11 s | 137 / 753 / 465 / 68 / 1 s |
| **Einzelmessung: unser Prompt, Schema, Tools** | 3–11 s | 3–4 s |
| **Einzelanfrage nach Tool-Ergebnis** | instabil | 2–8 s |

- Die Hänger traten auch allein auf, nicht nur unter paralleler Last: Bei
  `mistral-large-4-0` hing Zug 2 nach dem Tool-Aufruf trotz `200 OK` bis zum Testlimit
  von 4,5 Minuten beim Lesen der Antwort.
- `mistral-large-4-0` ruft nach dem Tool-Ergebnis teils das Tool erneut auf oder schreibt
  über 5.000 Zeichen bis zum gesetzten Limit von 1.500 Tokens (`finish_reason=length`).
- **Gefolgerte, nicht direkt belegte Ursache der Minuten:** entgleiste Ausgabe ohne
  Token-Limit und Timeout (siehe Abschnitt 8). Für `mistral-medium-3-5` ist die Ursache offen.
- Ob die langen Antworten von Mistral oder vom Fallback stammen, ist nicht geklärt. Die
  beiden Scores sind kein Qualitätsurteil.
- OpenRouter leitet bereits an den Anbieter Mistral weiter. Die direkte Mistral-API wurde
  nicht getestet, es liegt kein Key vor. Sie wäre vor allem für die Frage der
  EU-Verarbeitung relevant; das ist nicht bestätigt, und die Embeddings blieben davon unberührt.

### `gemini-3.8-flash`, `gpt-6.1-terra`, `claude-sonnet-5.5`
- `gemini-3.8-flash`: bester Schnitt, aber mehr als doppelt so langsam wie `gpt-4.1`.
- `gpt-6.1-terra`: bestanden, vom Maintainer wegen der Kosten gestrichen.
- `claude-sonnet-5.5`: vor dem Ergebnis abgebrochen, weil zu teuer. Laut Anthropic
  [Abschaltung frühestens 2027-09-28](https://platform.claude.com/docs/en/models/sonnet-5-5/overview).

### `gpt-5.6-luna` und `gemini-3.5-flash-lite`
Vergleich in Abschnitt 9.

## 6. Fakten-Pipeline (Dry-Run)

Die Pipeline nutzt das Modell des Haupt-Agenten (`update_programme_facts.py:337`, `:1187`).
Pro Modell je ein Lauf.

| Modell | Abweichungen | Bewertung |
|---|---|---|
| `gpt-6-luna` (low) | `emba_x.programme_start` 2027-02-01 → 2027-02-02 | korrekt |
| `gpt-5.6-luna` (low) | wie oben, dazu `emba_x.structure` „56 Tage am Campus“ → „13 Wochen am Campus“ | Datum korrekt, **Struktur falsch**: `embax.ch` und `emba.unisg.ch` nennen 56 Tage |
| `gemini-3.5-flash-lite` (low) | keine | kein falscher Wert, korrigiert aber das Startdatum nicht |

**Separater Befund:** In `programme_facts.json` steht für emba X der 2027-02-01, die
[offizielle Fristen-Seite](https://emba.unisg.ch/bewerbung/fristen) nennt den 2. Februar 2027.
Warum die tägliche Pipeline mit `gpt-4.1` das nicht korrigiert hat, ist ungeklärt.

## 7. Zweiter Judge: `google/gemini-2.5-flash`

Neu bewertet wurden vorhandene Antworten, je Fall eine Antwort und zwei Bewertungen.
Keine neuen Modellaufrufe des Haupt-Agenten.

| Modell | Schnitt Judge `gpt-4.1` | Schnitt Judge Gemini | Schlechtester Fall (Gemini) |
|---|---|---|---|
| `gpt-4.1` | 9,09 | **9,59** | 9,0 |
| `gemini-3.5-flash-lite` | 9,09 | 9,32 | 8,5 |
| `gpt-5.6-luna` | 9,18 | 9,27 | 7,0 |

- Der Schnitt mit Judge `gpt-4.1` weicht teils von Abschnitt 3 ab, weil für einige Fälle
  die jeweils letzte gespeicherte Antwort bewertet wurde.
- **Die 7,0 bei `gpt-5.6-luna` (TC-IEMBA-02) ist ein Judge-Fehler:** Kriterien
  (10 / 5 Jahre) und Gebühren (CHF 110'000 / 99'000) stimmen mit `programme_facts.json` überein.
- Bei `gemini-3.5-flash-lite` bewertet ein Gemini-Modell ein Gemini-Modell; das ist keine
  ganz neutrale Prüfung.
- **Judge-Stabilität (`gpt-4.1`):** Vier Antworten aus TC-EDGE-01 wurden je sechsmal neu
  bewertet, Abweichung höchstens 0,5. Die Streuung zwischen Läufen kommt also von den
  Antworten des Modells, nicht vom Judge.

## 8. Weitere Befunde

- **Fehlende Begrenzung im Produktivpfad:** Der OpenRouter-Pfad in `src/rag/models.py`
  setzt weder Timeout noch `max_tokens`; `_openai_budget` greift nur beim direkten
  OpenAI-Pfad. Es gilt der Standard des OpenAI-Clients (600 s Lesezeit). Eine hängende
  Anfrage kann also auch mit `gpt-4.1` bis zu 10 Minuten dauern. Eigenes Thema,
  unabhängig vom Modellwechsel.
- **OpenRouter-Key:** Ohne `max_tokens` reserviert OpenRouter das Output-Maximum des
  Modells. Bei nur noch $0,19 Rest-Limit lieferte `gpt-4.1` deshalb `402`, mit
  `max_tokens: 200` lief es. Die Tests verbrauchten bis dahin $10,41. Ob Produktion
  denselben Key nutzt, wurde nicht geprüft.
- **Testfall TC-IEMBA-01:** Bei `gemini-3.5-flash-lite` kostet in der gelesenen 8,0-Antwort
  vor allem fehlende Visa-Information Punkte, unsere Produktregel verlangt dort aber den
  Verweis an Admissions. Dort fehlten allerdings die Kontaktdaten. Die beiden 7,5-Antworten
  liegen nicht mehr vor.
- **`scripts/rubric_judge.py`:** Der Judge der Wochenberichte steht auf `gpt-4o-mini` und
  muss vor der Abschaltung umgestellt werden.

## 9. Auswertung

| Kriterium | `gemini-3.5-flash-lite` | `gpt-5.6-luna` | Vorteil |
|---|---|---|---|
| Falsche Fakten im Chat | 34/34, keine gefunden | 34/34, keine gefunden | gleich |
| UAT-Schnitt (`gpt-4.1` / Gemini) | 9,14 / 9,32 | 9,27 / 9,27 | praktisch gleich |
| Median pro Antwort | 3,54 s | 6,87 s | **Flash Lite** |
| Fakten-Pipeline | kein falscher Wert | 1 falscher Wert | **Flash Lite** |
| TC-IEMBA-01 unter 8,0 | 2 von 6 | 0 von 6 | `gpt-5.6-luna` |
| Kosten (In/Out) | $0,30 / $2,50 | $0,20 / $1,20 | `gpt-5.6-luna` |

**Begründung:** Die Qualität liegt gleichauf. Flash Lite ist fast doppelt so schnell und
hält das heutige Tempo von `gpt-4.1`, dazu erzeugte es in der Pipeline keinen falschen
Wert. Gegenüber `gpt-4.1` sinken die Kosten deutlich. Mit Judge `gemini-2.5-flash` liegt
`gpt-4.1` allerdings bei beiden Kandidaten vorn (Abschnitt 7).

**Restrisiko:** TC-IEMBA-01 kann die PR-Prüfung reißen. Dann wäre zuerst der Testfall zu
prüfen (Visa-Erwartung gegen Produktregel).

## 10. Testfall TC-IEMBA-01 korrigiert

Die Visa-Erwartung im Testfall widersprach der Produktregel in `src/rag/prompts.py:160`
(Verweis an das Admissions-Team, keine eigenen Visa-Details). In allen 10 geprüften
Läufen mit Flash Lite zog der Judge dafür ab. Geändert in `tests/fixtures/UAT.xlsx`,
Blatt `IEMBA`:

- **C16:** „Verweist an das Admissions-Team“, „Keine eigenen Visa-Details (Permit, Timeline, Dokumente)“
- **F5:** „Visa-Frage wird an das Admissions-Team verwiesen“

Dieselben 10 Antworten neu bewertet: vorher neunmal 8,5 und einmal 7,5, nachher zehnmal 9,5.
Die früheren TC-IEMBA-01-Scores aller Modelle in diesem Dokument stammen noch mit der
alten Erwartung.

## 11. Umsetzung (Branch `chore/migrate-to-gemini-flash-lite`)

Freigegeben vom Maintainer am 2026-11-05.

| Rolle | Modell |
|---|---|
| Haupt-Agent, Zusammenfassung, Fakten-Pipeline | `google/gemini-3.5-flash-lite`, Effort `low` |
| Spracherkennung, Confidence-Scoring | `google/gemini-3.5-flash-lite` |
| Fallback | `openai/gpt-5.6-luna`, Effort `low` |

Gates mit dieser Konfiguration:

| Gate | Ergebnis |
|---|---|
| Offline-Tests | 391 bestanden, 1 übersprungen |
| Fact-Eval | 34/34 |
| UAT | bestanden: Schnitt 9,09, schlechtester Fall 8,0 (TC-EDGE-04), Median 3,1 s |
| Streaming (8 Fragen DE/EN) | erstes Token 1,0–3,0 s, gesamt 1,5–3,8 s, 2–8 Teile pro Antwort, keine Warnungen, nur Flash Lite antwortete |
| Fakten-Pipeline (Dry-Run) | keine Abweichung zu `programme_facts.json` |
| Abschalttermin | Gemini API: nicht angekündigt; [Google Cloud](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-versions): frühestens 2027-07-21 |

## 12. Offene Punkte

- [ ] PR-Prüfung (UAT-Judge in der CI)
- [ ] Ausfall des Hauptmodells simulieren, um den Fallback `gpt-5.6-luna` im echten Ablauf zu prüfen
- [ ] emba-X-Startdatum in `programme_facts.json` klären (2027-02-01 statt 2. Februar 2027); Flash Lite korrigiert es nicht
- [ ] CI-Judge (`UAT_JUDGE_MODEL`) und `scripts/rubric_judge.py` vor der Abschaltung von `gpt-4.1`/`gpt-4o-mini` umstellen
- [ ] Timeout und `max_tokens` für den OpenRouter-Pfad setzen
- [ ] Abschalttermin von `gpt-4.1` offiziell bestätigen
- [ ] `docs/datenschutz_deployment.md` überarbeiten (Maintainer); neu werden Anfragen über OpenRouter an Google weitergeleitet

## Quellen

- [OpenRouter: Modellliste und Preise](https://openrouter.ai/api/v1/models), abgerufen 2026-11-05
- [Anthropic: Model deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations)
- [OpenAI Deprecations (Spiegel)](https://hn.jakechampion.name/reader/https://platform.openai.com/docs/deprecations)
- [Sessionwatcher: Abschaltung GPT-4o und GPT-4.1](https://sessionwatcher.com/news/openai-api-gpt-4o-gpt-4-1-shutdown-january-14-2027)
