import re
from datetime import datetime

from langchain_core.messages import AIMessage, HumanMessage

from src.config import config
from src.rag.chain_components import ChainComponent
from src.rag.programme_facts import ProgrammeFacts, ProgrammeFactsProvider
from src.rag.response_formatter import ResponseFormatter
from src.rag.utilclasses import LeadAgentQueryResponse
from src.utils.logging import get_logger

chain_logger = get_logger('agent_chain')


class ProgrammeFactResponses(ChainComponent):
    def _is_programme_fact_request(self, query: str) -> bool:
        query_lower = query.lower()
        fact_terms = [
            "kostet",
            "kosten",
            "preis",
            "preise",
            "gebühr",
            "gebuehr",
            "studiengebühr",
            "studiengebuehr",
            "chf",
            "wann",
            "beginnt",
            "startet",
            "start",
            "startdatum",
            "datum",
            "daten",
            "frist",
            "fristen",
            "bewerbungsfrist",
            "bewerbungszeitraum",
            "bewerbungsperiode",
            "bewerbungsprozess",
            "bewerbungsablauf",
            "bewerbungsunterlagen",
            "bewerbung",
            "bewerbe",
            "bewerben",
            "prozess",
            "ablauf",
            "schritte",
            "unterlagen",
            "dokumente",
            "deadline",
            "deadlines",
            "application period",
            "application process",
            "admissions process",
            "application documents",
            "application steps",
            "documents",
            "how do i apply",
            "how to apply",
            "dauer",
            "wie lange",
            "cost",
            "costs",
            "price",
            "tuition",
            "fee",
            "fees",
            "when",
            "begin",
            "starts",
            "start date",
            "date",
            "dates",
            "duration",
            "how long",
        ]
        return any(term in query_lower for term in fact_terms)

    def _resolve_programmes_for_fact_request(self, query: str) -> list[str]:
        if self._is_explicit_booking_intent(query):
            return []

        if self._is_application_next_step_route(query):
            return []

        if not self._is_programme_fact_request(query):
            return []

        programmes = self._extract_programmes_from_text(query)
        if programmes:
            return programmes

        if self._is_multi_programme_fact_request(query):
            return ["emba", "iemba", "emba_x"]

        programme_interest = self._conversation_state.get("program_interest") or []
        normalised_interests = []
        for item in programme_interest:
            programme = self._normalise_programme_id(item)
            if programme and programme not in normalised_interests:
                normalised_interests.append(programme)
        if normalised_interests:
            return normalised_interests

        programme = self._normalise_programme_id(
            self._conversation_state.get("suggested_program")
        )
        if programme:
            return [programme]

        if self._state_supports_emba_hsg_follow_up(query):
            return ["emba"]

        for message in reversed(self._conversation_history):
            if not isinstance(message, AIMessage):
                continue
            message_programmes = self._extract_programmes_from_text(message.content)
            if len(message_programmes) == 1:
                return message_programmes
            if len(message_programmes) > 1:
                return message_programmes

        return []

    def _state_supports_emba_hsg_follow_up(self, query: str) -> bool:
        query_lower = query.lower()
        generic_reference = any(
            term in query_lower
            for term in ["das programm", "dieses programm", "the programme", "the program"]
        ) or re.search(r"\bit\b", query_lower) is not None
        if not generic_reference:
            return False

        state = getattr(self, "_conversation_state", {}) or {}
        experience_years = state.get("experience_years")
        leadership_years = state.get("leadership_years")
        if not experience_years or experience_years < 5:
            return False
        if not leadership_years or leadership_years < 3:
            return False
        if state.get("program_interest"):
            return False

        context_lower = self._human_context_for_recommendation(query)
        disqualifying_goal_terms = [
            "international",
            "global",
            "englisch",
            "english",
            "technology",
            "technologie",
            "digital",
            "innovation",
            "transformation",
            "sustainability",
            "nachhaltigkeit",
            "eth",
        ]
        if any(term in context_lower for term in disqualifying_goal_terms):
            return False

        return getattr(self, "_stored_language", None) == "de" or "berufsbegleitend" in context_lower

    @staticmethod
    def _is_multi_programme_fact_request(query: str) -> bool:
        query_lower = query.lower()
        multi_terms = [
            "programme",
            "programmen",
            "programms",
            "programme jeweils",
            "jeweils",
            "alle",
            "alle drei",
            "vergleich",
            "vergleichen",
            "programmes",
            "programs",
            "each",
            "respectively",
            "all three",
            "compare",
        ]
        return any(term in query_lower for term in multi_terms)

    def _build_programme_fact_response(self, programme: str, language: str, query: str) -> str:
        programme_name, _ = self._programme_label_and_advisor(programme)
        categories = self._requested_fact_categories(query, language)
        if categories == ["cost"]:
            current_tuition = self._current_tuition_value(programme, language)
            if current_tuition:
                display_name = (
                    "emba X (ETH Zürich + Universität St.Gallen)"
                    if programme == "emba_x" and language == "de"
                    else "emba X (ETH Zurich + University of St.Gallen)"
                    if programme == "emba_x"
                    else programme_name
                )
                return self._format_requested_fact_block(
                    display_name,
                    "cost",
                    [current_tuition],
                    language,
                )
        context = self._get_targeted_programme_fact_context(programme, language, query, categories)
        facts_by_category = self._extract_requested_programme_facts(
            context=context,
            programme=programme,
            categories=categories,
            language=language,
        )
        if self._needs_cross_programme_fact_context(facts_by_category, categories):
            fallback_context = self._get_cross_programme_fact_context(language, categories)
            if fallback_context:
                facts_by_category = self._extract_requested_programme_facts(
                    context=f"{context}\n{fallback_context}",
                    programme=programme,
                    categories=categories,
                    language=language,
                )

        blocks = [
            self._format_requested_fact_block(
                programme_name,
                category,
                facts_by_category.get(category),
                language,
            )
            for category in categories
        ]
        return "\n\n".join(blocks)

    def _current_tuition_value(self, programme: str, language: str) -> str | None:
        facts = self._get_programme_facts(programme, language)
        value = facts.structured.get("tuition") if facts.structured else None
        if isinstance(value, str) and value.strip():
            return self._format_tuition_for_language(value.strip(), language)
        if isinstance(value, list) and value:
            return self._format_tuition_for_language(str(value[-1]).strip(), language)
        return None

    @staticmethod
    def _format_tuition_for_language(value: str, language: str) -> str:
        separator = "'" if language == "de" else ","

        def normalize(match: re.Match[str]) -> str:
            compact = re.sub(r"\D", "", match.group(1))
            if len(compact) <= 3:
                return f"CHF {compact}"
            return f"CHF {compact[:-3]}{separator}{compact[-3:]}"

        return re.sub(
            r"CHF\s*([0-9][0-9'.,\s]*[0-9])",
            normalize,
            value,
            count=1,
            flags=re.IGNORECASE,
        )

    def _requested_fact_categories(self, query: str, language: str) -> list[str]:
        query_lower = query.lower()
        categories: list[str] = []

        cost_terms = [
            "kostet",
            "kosten",
            "preis",
            "preise",
            "gebühr",
            "gebuehr",
            "studiengebühr",
            "studiengebuehr",
            "chf",
            "cost",
            "costs",
            "price",
            "tuition",
            "fee",
            "fees",
        ]
        start_terms = [
            "beginnt",
            "startet",
            "startdatum",
            "startdaten",
            "programm-start",
            "program start",
            "beginn",
            "start date",
            "starts",
            "begin",
        ]
        deadline_terms = [
            "wann soll ich mich",
            "bewerbungsfrist",
            "bewerbungszeitraum",
            "bewerbungsperiode",
            "frist",
            "fristen",
            "deadline",
            "deadlines",
            "application deadline",
            "application period",
        ]
        application_process_terms = [
            "wie bewerbe ich mich",
            "wie bewirbt man sich",
            "bewerbe ich mich",
            "wie läuft die bewerbung",
            "wie laeuft die bewerbung",
            "bewerbungsprozess",
            "bewerbungsablauf",
            "bewerbung ab",
            "prozess",
            "ablauf",
            "schritte",
            "how do i apply",
            "how to apply",
            "application process",
            "admissions process",
            "application steps",
        ]
        document_terms = [
            "bewerbungsunterlagen",
            "unterlagen",
            "dokument",
            "dokumente",
            "cv",
            "lebenslauf",
            "zeugnis",
            "zeugnisse",
            "transcript",
            "transcripts",
            "application documents",
            "documents",
        ]
        duration_terms = [
            "dauer",
            "wie lange",
            "duration",
            "how long",
        ]
        admission_terms = [
            "zulassung",
            "zulassungsdetails",
            "voraussetzung",
            "voraussetzungen",
            "admission",
            "admissions",
            "requirements",
        ]

        if any(term in query_lower for term in application_process_terms) or re.search(
            r"\bwie\b.{0,100}\b(bewerben|bewerbe|bewerbung|bewirbt)\b",
            query_lower,
        ) or re.search(
            r"\bhow\b.{0,100}\b(apply|application|admission|admissions)\b",
            query_lower,
        ):
            categories.extend(["application_process", "documents", "deadline"])
        elif any(term in query_lower for term in document_terms):
            categories.append("documents")

        category_terms = [
            ("cost", cost_terms),
            ("start", start_terms),
            ("deadline", deadline_terms),
            ("duration", duration_terms),
            ("admission", admission_terms),
        ]
        for category, terms in category_terms:
            if any(term in query_lower for term in terms):
                categories.append(category)

        if not categories and any(term in query_lower for term in ["wann", "when", "datum", "date", "daten", "dates"]):
            categories.extend(["start", "deadline"])

        if not categories:
            categories.extend(["cost", "start", "deadline", "duration"])

        return categories

    def _get_targeted_programme_fact_context(
        self,
        programme: str,
        language: str,
        user_query: str,
        categories: list[str],
    ) -> str:
        targeted_query = self._build_targeted_fact_query(
            user_query=user_query,
            categories=categories,
            language=language,
            programme=programme,
        )
        program_filter = ProgrammeFactsProvider._PROGRAM_FILTERS.get(programme, programme)
        can_retrieve = hasattr(self, "_retrieve_context_tool") or hasattr(self, "_dbservice")

        if can_retrieve:
            try:
                context = self._retrieve_context_via_tool(
                    query=targeted_query,
                    program=program_filter,
                    language=language,
                )
                if context:
                    return context
            except Exception as exc:
                chain_logger.warning(
                    "Targeted programme fact retrieval failed for %s: %s",
                    programme,
                    exc,
                )

        facts = self._get_programme_facts(programme, language)
        fallback_points = facts.timing_points + facts.document_points
        if any(category in categories for category in ["admission", "application_process"]):
            fallback_points.extend(facts.fit_points)
        return "\n".join(fallback_points or [facts.raw_context])

    def _get_cross_programme_fact_context(self, language: str, categories: list[str]) -> str:
        if not (hasattr(self, "_retrieve_context_tool") or hasattr(self, "_dbservice")):
            return ""

        cache_key = (language, tuple(categories))
        cache = getattr(self, "_programme_fact_context_cache", None)
        if cache is None:
            cache = {}
            self._programme_fact_context_cache = cache
        if cache_key in cache:
            return cache[cache_key]

        query = self._build_cross_programme_fact_query(categories, language)
        try:
            context = self._retrieve_context_via_tool(
                query=query,
                program="emba",
                language=language,
            ) or ""
        except Exception as exc:
            chain_logger.warning("Cross-programme fact retrieval failed: %s", exc)
            context = ""

        cache[cache_key] = context
        return context

    @staticmethod
    def _build_cross_programme_fact_query(categories: list[str], language: str) -> str:
        if language == "en":
            base = "application deadlines tuition CHF programme start EMBA HSG IEMBA HSG emba X"
            extras = {
                "cost": "tuition fee CHF",
                "start": "programme start start date",
                "deadline": "application deadline",
                "duration": "duration months",
                "admission": "admission requirements",
                "application_process": "application process how to apply documents submit application",
                "documents": "application documents CV certificates transcripts online application assessment",
            }
        else:
            base = "Bewerbungsfristen im Überblick Studiengebühr Programm-Start CHF EMBA HSG IEMBA HSG emba X"
            extras = {
                "cost": "Studiengebühr CHF",
                "start": "Programm-Start Startdatum",
                "deadline": "Bewerbungsfrist Bewerbung",
                "duration": "Dauer Monate",
                "admission": "Zulassung Voraussetzungen",
                "application_process": "Bewerbungsprozess Bewerbung bewerben Unterlagen einreichen",
                "documents": "Bewerbungsunterlagen Unterlagen Dokumente CV Lebenslauf Zeugnisse Online-Bewerbung Online-Assessment",
            }
        return " ".join([base] + [extras.get(category, "") for category in categories]).strip()

    @staticmethod
    def _has_missing_requested_facts(facts_by_category: dict[str, list[str]], categories: list[str]) -> bool:
        return any(not facts_by_category.get(category) for category in categories)

    @staticmethod
    def _needs_cross_programme_fact_context(
        facts_by_category: dict[str, list[str]],
        categories: list[str],
    ) -> bool:
        if ProgrammeFactResponses._has_missing_requested_facts(facts_by_category, categories):
            return True

        cost_values = facts_by_category.get("cost") or []
        if "cost" in categories and cost_values and not any(":" in value for value in cost_values):
            return True

        return False

    @staticmethod
    def _build_targeted_fact_query(
        user_query: str,
        categories: list[str],
        language: str,
        programme: str,
    ) -> str:
        programme_terms = {
            "emba": "EMBA HSG EMBA 71 Executive MBA HSG",
            "iemba": "IEMBA HSG IEMBA 14 International EMBA HSG",
            "emba_x": "emba X EMBA ETH HSG",
        }
        query_parts = [programme_terms.get(programme, programme)]
        if language == "en":
            terms_by_category = {
                "cost": "tuition fee cost price CHF",
                "start": "programme start date next intake begins",
                "deadline": "application deadline application due date apply by",
                "duration": "duration months programme length",
                "admission": "admission requirements eligibility degree experience language",
                "application_process": "application process how to apply admissions process application steps submit application enrolment",
                "documents": "application documents CV certificates transcripts degree motivation online application assessment documents",
            }
        else:
            terms_by_category = {
                "cost": "Studiengebühr Gebühren Bewerbungsfrist Programmstart Programm-Start CHF",
                "start": "Startdatum Programmstart nächster Start Beginn beginnt",
                "deadline": "Bewerbungsfrist Frist Bewerbung bewerben",
                "duration": "Dauer Monate Programmdauer",
                "admission": "Zulassung Voraussetzungen Anforderungen Abschluss Erfahrung Sprache",
                "application_process": "Bewerbungsprozess Bewerbung bewerben Zulassungsprozess Ablauf Schritte einreichen Einschreibung",
                "documents": "Bewerbungsunterlagen Unterlagen Dokumente CV Lebenslauf Zeugnisse Abschluss Motivation Online-Bewerbung Online-Assessment",
            }

        for category in categories:
            query_parts.append(terms_by_category.get(category, ""))
        return " ".join(part for part in query_parts if part).strip()

    def _extract_requested_programme_facts(
        self,
        context: str,
        programme: str,
        categories: list[str],
        language: str,
    ) -> dict[str, list[str]]:
        sentences = self._programme_relevant_fact_sentences(context, programme)
        extracted: dict[str, list[str]] = {}
        for category in categories:
            extracted[category] = self._extract_values_for_fact_category(
                sentences,
                category,
                language,
                programme,
            )
        return extracted

    def _programme_relevant_fact_sentences(self, context: str, programme: str) -> list[str]:
        section_sentences = self._programme_section_fact_sentences(context, programme)
        raw_neutral_sentences = [
            self._clean_fact_sentence(re.sub(r"#{1,6}\s*", "", line))
            for line in re.split(r"\n+", context or "")
            if line.strip()
        ]
        raw_neutral_sentences = [
            sentence
            for sentence in raw_neutral_sentences
            if sentence
            and not self._sentence_mentions_any_programme(sentence)
            and not self._is_noise_fact_sentence(sentence)
        ]
        sentences = [
            self._clean_fact_sentence(sentence)
            for sentence in ProgrammeFactsProvider._split_sentences(context)
        ]
        sentences = [sentence for sentence in sentences if sentence]

        programme_sentences = [
            sentence
            for sentence in sentences
            if self._sentence_matches_programme(sentence, programme)
            and not self._sentence_mentions_other_programme(sentence, programme)
        ]
        neutral_sentences = [
            sentence
            for sentence in sentences
            if not self._sentence_mentions_any_programme(sentence)
        ]
        fallback_sentences = [
            sentence
            for sentence in sentences
            if not self._sentence_mentions_other_programme(sentence, programme)
        ]

        if section_sentences:
            return self._unique_texts(section_sentences + programme_sentences)

        return self._unique_texts(programme_sentences + raw_neutral_sentences + neutral_sentences + fallback_sentences)

    def _programme_section_fact_sentences(self, context: str, programme: str) -> list[str]:
        section_sentences = []
        in_target_section = False
        pending_label = ""
        raw_lines = re.split(r"\n+", context or "")

        for raw_line in raw_lines:
            line = self._clean_fact_sentence(re.sub(r"#{1,6}\s*", "", raw_line))
            if not line:
                continue
            if self._is_noise_fact_sentence(line):
                in_target_section = False
                pending_label = ""
                continue

            mentions_any_programme = self._sentence_mentions_any_programme(line)
            if mentions_any_programme:
                in_target_section = self._sentence_matches_programme(line, programme)
                pending_label = ""
                if in_target_section:
                    section_sentences.append(line)
                continue

            if in_target_section:
                label = self._fact_line_label(line)
                if label:
                    pending_label = label
                    section_sentences.append(line)
                    continue
                if pending_label:
                    section_sentences.append(f"{pending_label} {line}")
                    pending_label = ""
                section_sentences.append(line)

        return self._unique_texts(section_sentences)

    @staticmethod
    def _is_noise_fact_sentence(sentence: str) -> bool:
        sentence_lower = sentence.lower()
        return any(term in sentence_lower for term in ProgrammeFactsProvider._NOISE_TERMS)

    @staticmethod
    def _fact_line_label(line: str) -> str:
        normalized = line.strip(" :").lower()
        labels = {
            "beginn": "Beginn",
            "start": "Start",
            "gebühr": "Gebühr",
            "gebuehr": "Gebühr",
            "studiengebühr": "Studiengebühr",
            "studiengebuehr": "Studiengebühr",
            "dauer": "Dauer",
            "duration": "Duration",
            "tuition": "Tuition",
            "fee": "Fee",
        }
        return labels.get(normalized, "")

    @staticmethod
    def _clean_fact_sentence(sentence: str) -> str:
        cleaned = re.sub(r"\s+", " ", sentence or "").strip(" -;:.,\t\n")
        cleaned = re.sub(r"\b\d+\.\s*;\s*", "", cleaned)
        cleaned = re.sub(r"\s+([:;,.])", r"\1", cleaned)
        cleaned = re.sub(r"([:;])\s*([:;])+", r"\1", cleaned)
        return cleaned.strip()

    @staticmethod
    def _sentence_matches_programme(sentence: str, programme: str) -> bool:
        sentence_lower = sentence.lower()
        if programme == "emba_x":
            return "emba x" in sentence_lower or "embax" in sentence_lower or "emba eth hsg" in sentence_lower
        if programme == "iemba":
            return (
                "iemba" in sentence_lower
                or "international emba" in sentence_lower
                or "international executive mba" in sentence_lower
            )
        if programme == "emba":
            return (
                bool(re.search(r"(?<!i)\bemba hsg\b", sentence_lower))
                or bool(re.search(r"(?<!i)\bemba\s*\d+\b", sentence_lower))
                or "executive mba hsg" in sentence_lower
            )
        return False

    @staticmethod
    def _sentence_mentions_any_programme(sentence: str) -> bool:
        sentence_lower = sentence.lower()
        return bool(
            "emba x" in sentence_lower
            or "embax" in sentence_lower
            or "emba eth hsg" in sentence_lower
            or "iemba" in sentence_lower
            or "international emba" in sentence_lower
            or "international executive mba" in sentence_lower
            or re.search(r"(?<!i)\bemba hsg\b", sentence_lower)
            or re.search(r"(?<!i)\bemba\s*\d+\b", sentence_lower)
        )

    def _sentence_mentions_other_programme(self, sentence: str, programme: str) -> bool:
        sentence_lower = sentence.lower()
        if programme != "emba_x" and (
            "emba x" in sentence_lower
            or "embax" in sentence_lower
            or "emba eth hsg" in sentence_lower
        ):
            return True
        if programme != "iemba" and (
            "iemba" in sentence_lower
            or "international emba" in sentence_lower
            or "international executive mba" in sentence_lower
        ):
            return True
        if programme != "emba" and re.search(r"(?<!i)\bemba hsg\b", sentence_lower):
            return True
        return False

    def _extract_values_for_fact_category(
        self,
        sentences: list[str],
        category: str,
        language: str,
        programme: str | None = None,
    ) -> list[str]:
        terms_by_category = {
            "cost": (
                "studiengebühr",
                "studiengebuehr",
                "gebühr",
                "gebuehr",
                "kosten",
                "preis",
                "tuition",
                "fee",
                "fees",
                "cost",
                "price",
                "chf",
            ),
            "start": (
                "start",
                "programmstart",
                "programm-start",
                "beginn",
                "beginnt",
                "startet",
                "intake",
            ),
            "deadline": (
                "bewerbungsfrist",
                "frist",
                "deadline",
                "apply",
                "application",
                "bewerbung",
                "bewerben",
            ),
            "duration": (
                "dauer",
                "monate",
                "months",
                "programmdauer",
                "duration",
                "programme length",
            ),
            "admission": (
                "zulassung",
                "voraussetzung",
                "anforderung",
                "abschluss",
                "erfahrung",
                "admission",
                "requirement",
                "degree",
                "experience",
            ),
            "application_process": (
                "bewerbungsprozess",
                "bewerben",
                "zulassungsprozess",
                "einreichen",
                "einschreibung",
                "application process",
                "apply",
                "submit",
                "admissions process",
                "enrol",
                "enroll",
            ),
            "documents": (
                "bewerbungsunterlagen",
                "unterlagen",
                "dokument",
                "dokumente",
                "cv",
                "lebenslauf",
                "zeugnis",
                "zeugnisse",
                "certificate",
                "certificates",
                "transcript",
                "transcripts",
                "documents",
            ),
        }
        category_terms = terms_by_category.get(category, ())
        if category == "cost":
            current_tuition = self._current_tuition_value(programme, language)
            if current_tuition:
                return [current_tuition]

        candidates = [
            sentence
            for sentence in sentences
            if any(term in sentence.lower() for term in category_terms)
        ]
        if category in {"application_process", "documents"}:
            candidates = [
                sentence
                for sentence in candidates
                if not self._is_noise_fact_sentence(sentence)
            ]
            candidates = sorted(
                candidates,
                key=self._score_application_fact_candidate,
                reverse=True,
            )

        if category == "cost":
            values = self._unique_texts(
                value
                for sentence in candidates
                if not self._sentence_has_only_past_years(sentence)
                for value in self._extract_cost_values(sentence, language)
            )
            deadline_linked_values = [value for value in values if ":" in value]
            if deadline_linked_values:
                return deadline_linked_values
            if values:
                return values

            return []
        if category in {"start", "deadline"}:
            values = self._unique_texts(
                value
                for sentence in candidates
                for value in self._extract_future_dates(sentence)
            )
            if category == "start":
                exact_values = [
                    value
                    for value in values
                    if not re.search(r"\b(?:Herbst|Frühjahr|Fruehjahr|Sommer|Winter|Fall|Autumn|Spring)\b", value, flags=re.IGNORECASE)
                ]
                if exact_values:
                    return exact_values
            return values
        if category == "duration":
            return self._unique_texts(
                value
                for sentence in candidates
                for value in self._extract_duration_values(sentence, language)
            )
        if category == "admission":
            return self._unique_texts(
                self._shorten_fact_sentence(sentence)
                for sentence in candidates[:3]
            )
        if category == "application_process":
            return self._unique_texts(
                self._format_application_process_fact(sentence)
                for sentence in candidates[:3]
            )
        if category == "documents":
            document_values = self._unique_texts(
                value
                for sentence in candidates
                for value in self._extract_application_document_values(sentence, language)
            )
            if document_values:
                return document_values
            return self._unique_texts(
                self._shorten_fact_sentence(sentence)
                for sentence in candidates[:3]
            )
        return []

    @staticmethod
    def _extract_chf_amounts(sentence: str, language: str) -> list[str]:
        amounts = re.findall(
            r"CHF\s*\d{1,3}(?:[\s,'’`]\d{3})+(?:\.\d{2})?|CHF\s*\d+",
            sentence,
            flags=re.IGNORECASE,
        )
        normalized = []
        for amount in amounts:
            normalized_amount = re.sub(r"\s+", " ", amount.strip())
            normalized_amount = normalized_amount.replace("’", "'").replace("`", "'")
            normalized_amount = re.sub(r"CHF\s+", "CHF ", normalized_amount, flags=re.IGNORECASE)
            number_part = normalized_amount[4:].strip() if normalized_amount.lower().startswith("chf ") else normalized_amount
            number_part = number_part.replace(" ", "'")
            if language == "en":
                number_part = number_part.replace("'", ",")
            elif "," in number_part and "." not in number_part:
                number_part = number_part.replace(",", "'")
            digits_only = re.sub(r"\D", "", number_part)
            if digits_only and int(digits_only) < 10000:
                continue
            normalized.append(f"CHF {number_part}")
        return normalized

    @staticmethod
    def _extract_cost_values(sentence: str, language: str) -> list[str]:
        amounts = ProgrammeFactResponses._extract_chf_amounts(sentence, language)
        if not amounts:
            return []

        sentence_lower = sentence.lower()
        has_deadline_context = any(
            term in sentence_lower
            for term in ["bewerbungsfrist", "frist", "deadline", "application deadline"]
        )
        dates = ProgrammeFactResponses._extract_future_dates(sentence)
        if has_deadline_context and dates and len(dates) >= len(amounts):
            return [f"{date}: {amount}" for date, amount in zip(dates, amounts)]

        return amounts

    @staticmethod
    def _extract_future_dates(sentence: str) -> list[str]:
        month_names = (
            "Januar|Februar|März|Maerz|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember|"
            "January|February|March|April|May|June|July|August|September|October|November|December"
        )
        season_names = "Herbst|Frühjahr|Fruehjahr|Sommer|Winter|Fall|Autumn|Spring"
        patterns = [
            rf"\b\d{{1,2}}[./]\d{{1,2}}[./]\d{{4}}\b",
            rf"\b\d{{1,2}}\.?\s+(?:{month_names})\s+\d{{4}}\b",
            rf"\b(?:{season_names})\s+\d{{4}}\b",
        ]

        dates = []
        for pattern in patterns:
            dates.extend(re.findall(pattern, sentence, flags=re.IGNORECASE))

        return [
            date.strip()
            for date in dates
            if ProgrammeFactResponses._date_has_current_or_future_year(date)
        ]

    @staticmethod
    def _date_has_current_or_future_year(value: str) -> bool:
        year_match = re.search(r"\b(20\d{2})\b", value)
        if not year_match:
            return False
        return int(year_match.group(1)) >= datetime.now().year

    @staticmethod
    def _sentence_has_only_past_years(sentence: str) -> bool:
        years = [int(year) for year in re.findall(r"\b(20\d{2})\b", sentence or "")]
        return bool(years) and max(years) < datetime.now().year

    @staticmethod
    def _extract_duration_values(sentence: str, language: str) -> list[str]:
        durations = re.findall(
            r"\b\d{1,2}\s*(?:Monate|months)\b",
            sentence,
            flags=re.IGNORECASE,
        )
        return [re.sub(r"\s+", " ", duration.strip()) for duration in durations]

    @staticmethod
    def _format_application_process_fact(sentence: str) -> str:
        sentence = re.sub(r"\s+", " ", sentence).strip(" .")
        if re.search(r"\b1\.\s+", sentence) and re.search(r"\b2\.\s+", sentence):
            parts = re.split(r"\s+\d+\.\s+", re.sub(r"^\s*1\.\s+", "", sentence))
            cleaned_parts = [
                re.sub(r"\s+", " ", part).strip(" .")
                for part in parts
                if part.strip()
            ]
            if cleaned_parts:
                return "; ".join(cleaned_parts[:5])
        return ProgrammeFactResponses._shorten_fact_sentence(sentence)

    @staticmethod
    def _extract_application_document_values(sentence: str, language: str) -> list[str]:
        sentence_lower = sentence.lower()
        values = []
        if "lebenslauf" in sentence_lower or re.search(r"\bcv\b", sentence_lower):
            values.append("Lebenslauf/CV zur Profilprüfung" if language == "de" else "CV for profile review")
        if "online-bewerbung" in sentence_lower or "online application" in sentence_lower:
            values.append("vollständig ausgefüllte Online-Bewerbung" if language == "de" else "completed online application")
        if "zeugnis" in sentence_lower or "certificate" in sentence_lower or "transcript" in sentence_lower:
            values.append("Zeugnisse/Studienabschluss" if language == "de" else "certificates/transcripts")
        if "motivation" in sentence_lower:
            values.append("Motivation" if language == "de" else "motivation")
        if "essay" in sentence_lower:
            values.append("Essay, falls Sie Zuschüsse beantragen" if language == "de" else "essay if applying for tuition support")
        return values

    @staticmethod
    def _score_application_fact_candidate(sentence: str) -> int:
        sentence_lower = sentence.lower()
        score = 0
        if re.search(r"\b1\.\s+", sentence) and re.search(r"\b2\.\s+", sentence):
            score += 8
        for term in [
            "lebenslauf",
            "cv",
            "online-bewerbung",
            "online application",
            "online-assessment",
            "online-interview",
            "zulassungsausschuss",
            "bewerbungsprozess",
            "application process",
        ]:
            if term in sentence_lower:
                score += 2
        if "jetzt bewerben" in sentence_lower:
            score -= 1
        return score

    @staticmethod
    def _shorten_fact_sentence(sentence: str) -> str:
        sentence = re.sub(r"\s+", " ", sentence).strip(" .")
        if len(sentence) <= 180:
            return sentence
        return sentence[:177].rstrip() + "..."

    @staticmethod
    def _unique_texts(values) -> list[str]:
        unique = []
        seen = set()
        for value in values:
            text = str(value).strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(text)
        return unique

    @staticmethod
    def _fact_category_label(category: str, language: str) -> str:
        labels = {
            "de": {
                "cost": "Kosten",
                "start": "Start",
                "deadline": "Bewerbungsfrist",
                "duration": "Dauer",
                "admission": "Zulassung",
                "application_process": "Bewerbungsprozess",
                "documents": "Unterlagen",
            },
            "en": {
                "cost": "Cost",
                "start": "Start",
                "deadline": "Application deadline",
                "duration": "Duration",
                "admission": "Admissions",
                "application_process": "Application process",
                "documents": "Documents",
            },
        }
        return labels.get(language, labels["en"]).get(category, category)

    @staticmethod
    def _format_requested_fact_values(values: list[str] | None, category: str, language: str) -> str:
        selected_values = ProgrammeFactResponses._selected_requested_fact_values(values, category)
        if selected_values:
            selected_values = [
                ProgrammeFactResponses._escape_markdown_ordered_list_marker(value)
                for value in selected_values
            ]
            if category == "cost":
                return "\n  - " + "\n  - ".join(selected_values)
            return "; ".join(selected_values)
        return ProgrammeFactResponses._empty_requested_fact_value(category, language)

    @staticmethod
    def _selected_requested_fact_values(values: list[str] | None, category: str) -> list[str]:
        if not values:
            return []

        if category == "cost":
            selected_values = [values[-1]]
        else:
            limits = {
                "start": 1,
                "deadline": 2,
                "duration": 1,
                "admission": 3,
                "application_process": 1,
                "documents": 3,
            }
            selected_values = values[:limits.get(category, 3)]

        return [
            " ".join(str(value).split())
            for value in selected_values
            if str(value).strip()
        ]

    @staticmethod
    def _escape_markdown_ordered_list_marker(value: str) -> str:
        return re.sub(r"^(\s*\d{1,9})\.(?=\s)", r"\1\\.", value)

    @staticmethod
    def _empty_requested_fact_value(category: str, language: str) -> str:
        if language == "en":
            empty = {
                "cost": "no reliable current tuition amount found",
                "start": "no reliable current start date found",
                "deadline": "no reliable current application deadline found",
                "duration": "no reliable programme duration found",
                "admission": "no reliable admissions detail found",
                "application_process": "no reliable current application process detail found",
                "documents": "no reliable current application document detail found",
            }
            return empty.get(category, "no reliable current detail found")

        empty = {
            "cost": "keine verlässliche aktuelle Kostenangabe gefunden",
            "start": "kein verlässliches aktuelles Startdatum gefunden",
            "deadline": "keine verlässliche aktuelle Bewerbungsfrist gefunden",
            "duration": "keine verlässliche Programmdauer gefunden",
            "admission": "keine verlässlichen Zulassungsdetails gefunden",
            "application_process": "keine verlässlichen aktuellen Angaben zum Bewerbungsprozess gefunden",
            "documents": "keine verlässlichen aktuellen Angaben zu Bewerbungsunterlagen gefunden",
        }
        return empty.get(category, "keine verlässliche aktuelle Angabe gefunden")

    def _format_requested_fact_block(
        self,
        programme_name: str,
        category: str,
        values: list[str] | None,
        language: str,
    ) -> str:
        topic = self._fact_category_label(category, language)
        selected_values = self._selected_requested_fact_values(values, category)
        if not selected_values:
            selected_values = [self._empty_requested_fact_value(category, language)]
        selected_values = [
            self._escape_markdown_ordered_list_marker(value)
            for value in selected_values
        ]
        bullets = "\n".join(f"- {value}" for value in selected_values)
        return f"**{programme_name} {topic}**:\n{bullets}"

    def _serve_programme_fact_request(
        self,
        processed_query: str,
        response_language: str,
        programmes: list[str],
    ) -> LeadAgentQueryResponse:
        chain_logger.info(f"Serving programme fact request via retrieve_context tool: {programmes}")
        responses = [
            self._build_programme_fact_response(programme, response_language, processed_query)
            for programme in programmes
        ]
        response = "\n\n".join(responses)
        response = ResponseFormatter.clean_response(ResponseFormatter.remove_tables(response))
        response = ResponseFormatter.format_name_of_university(response, language=response_language)

        self._pending_continuation = None
        self._conversation_history.append(HumanMessage(processed_query))
        self._conversation_history.append(AIMessage(response))

        return LeadAgentQueryResponse(
            response=response,
            language=response_language,
            confidence_fallback=False,
            should_cache=False,
            processed_query=processed_query,
        )

    def _get_programme_facts(self, programme: str, language: str) -> ProgrammeFacts:
        provider = getattr(self, "_programme_facts_provider", None)
        if provider is None:
            return ProgrammeFacts(programme=programme)
        return provider.get_facts(programme, language)

    def _get_programmes_facts(self, programmes: list[str], language: str) -> dict[str, ProgrammeFacts]:
        provider = getattr(self, "_programme_facts_provider", None)
        if provider is None:
            return {
                programme: ProgrammeFacts(programme=programme)
                for programme in programmes
            }

        get_facts_many = getattr(provider, "get_facts_many", None)
        if callable(get_facts_many):
            return get_facts_many(programmes, language)

        return {
            programme: provider.get_facts(programme, language)
            for programme in programmes
        }

    @staticmethod
    def _format_fact_points(points: list[str], fallback: str) -> str:
        if not points:
            return fallback
        return "; ".join(points)

    def _build_programme_fact_summary(self, programme: str, language: str) -> str:
        facts = self._get_programme_facts(programme, language)
        return self._build_programme_fact_summary_from_facts(programme, language, facts)

    def _build_programme_fact_summary_from_facts(
        self,
        programme: str,
        language: str,
        facts: ProgrammeFacts,
    ) -> str:
        programme_name, _ = self._programme_label_and_advisor(programme)
        if language == "en":
            focus = self._format_fact_points(
                facts.focus_points,
                "focus details are not clearly available in the current programme material",
            )
            fit = self._format_fact_points(
                facts.fit_points,
                "admissions requirements should be checked with the current admissions material",
            )
            timing = self._format_fact_points(
                facts.timing_points,
                "current duration, start, deadline, and tuition details are not clearly available in the current programme material",
            )
            return (
                f"**{programme_name}**: {focus}. "
                f"Format, timing, and tuition: {timing}. "
                f"Admissions fit: {fit}."
            )

        focus = self._format_fact_points(
            facts.focus_points,
            "Fokusdetails sind in den aktuellen Programmunterlagen gerade nicht eindeutig verfügbar",
        )
        fit = self._format_fact_points(
            facts.fit_points,
            "Zulassungsanforderungen sollten anhand des aktuellen Zulassungsmaterials geprüft werden",
        )
        timing = self._format_fact_points(
            facts.timing_points,
            "aktuelle Angaben zu Dauer, Start, Fristen und Gebühren sind in den Programmunterlagen gerade nicht eindeutig verfügbar",
        )
        return (
            f"**{programme_name}**: {focus}. "
            f"Format, Timing und Gebühren: {timing}. "
            f"Formaler Fit: {fit}."
        )

    @staticmethod
    def _programme_label_and_advisor(programme: str) -> tuple[str, str]:
        labels = {
            "emba": ("EMBA HSG", "the admissions team"),
            "iemba": ("IEMBA HSG", "the admissions team"),
            "emba_x": ("emba X", "the admissions team"),
        }
        return labels.get(programme, ("Executive MBA", "dem Admissions Team"))

    def _build_programme_next_steps_response(self, language: str, programme: str) -> str:
        programme_name, advisor = self._programme_label_and_advisor(programme)
        facts = self._get_programme_facts(programme, language)

        if language == "en":
            focus = self._format_fact_points(
                facts.focus_points,
                "the development goal should be clarified with admissions because the current programme material does not contain a clear focus summary",
            )
            fit = self._format_fact_points(
                facts.fit_points,
                "formal requirements should be confirmed from the current admissions material",
            )
            timing = self._format_fact_points(
                facts.timing_points,
                "current start, tuition, and deadline information is not clearly available in the programme material",
            )
            documents = self._format_fact_points(
                facts.document_points,
                "the required application documents should be confirmed in the admissions conversation",
            )
            return (
                f"If **{programme_name}** is currently the strongest option, the next step is a fit and admissions check.\n\n"
                f"1. **Clarify the development goal**: {focus}.\n"
                f"2. **Check formal fit**: {fit}.\n"
                f"3. **Plan timing and tuition**: {timing}.\n"
                f"4. **Prepare the admissions conversation**: {documents}.\n\n"
                f"The right advisor is **{advisor}** for **{programme_name}** if you want a personal consultation."
            )

        focus = self._format_fact_points(
            facts.focus_points,
            "das Entwicklungsziel sollte im Beratungsgespräch anhand der aktuellen Programmunterlagen geklärt werden",
        )
        fit = self._format_fact_points(
            facts.fit_points,
            "die formalen Anforderungen sollten anhand des aktuellen Zulassungsmaterials bestätigt werden",
        )
        timing = self._format_fact_points(
            facts.timing_points,
            "aktuelle Start-, Gebühren- und Fristdaten sind in den Programmunterlagen gerade nicht eindeutig verfügbar",
        )
        documents = self._format_fact_points(
            facts.document_points,
            "die erforderlichen Bewerbungsunterlagen sollten im Zulassungsgespräch bestätigt werden",
        )
        return (
            f"Wenn **{programme_name}** aktuell am besten passt, ist der nächste Schritt eine Fit- und Zulassungsabklärung.\n\n"
            f"1. **Ziel schärfen**: {focus}.\n"
            f"2. **Formalen Fit prüfen**: {fit}.\n"
            f"3. **Timing und Gebühren planen**: {timing}.\n"
            f"4. **Admissions-Gespräch vorbereiten**: {documents}.\n\n"
            f"Die passende Studienberatung ist **{advisor}** für **{programme_name}**, falls Sie eine persönliche Beratung wünschen."
        )

    def _serve_programme_next_steps(
        self,
        processed_query: str,
        response_language: str,
        programme: str,
    ) -> LeadAgentQueryResponse:
        chain_logger.info(f"Serving next-step guidance for selected programme: {programme}")
        response = self._build_programme_next_steps_response(response_language, programme)
        response = ResponseFormatter.format_name_of_university(response, language=response_language)
        response = ResponseFormatter.clean_response(response)

        self._pending_continuation = None
        self._conversation_history.append(HumanMessage(processed_query))
        self._conversation_history.append(AIMessage(response))
        self._conversation_state['suggested_program'] = programme
        return LeadAgentQueryResponse(
            response=response,
            language=response_language,
            confidence_fallback=False,
            should_cache=False,
            processed_query=processed_query,
        )

    def _get_application_timing_fact_values(
        self,
        programme: str,
        language: str,
    ) -> dict[str, list[str]]:
        categories = ["cost", "start", "deadline"]
        contexts: list[str] = []

        cross_context = self._get_cross_programme_fact_context(language, categories)
        if cross_context:
            contexts.append(cross_context)

        facts_by_category = self._extract_requested_programme_facts(
            context="\n".join(contexts),
            programme=programme,
            categories=categories,
            language=language,
        )

        if self._has_missing_requested_facts(facts_by_category, categories):
            targeted_context = self._get_targeted_programme_fact_context(
                programme=programme,
                language=language,
                user_query=(
                    "Bewerbungsfrist Studiengebühr Programm-Start"
                    if language == "de"
                    else "application deadline tuition programme start"
                ),
                categories=categories,
            )
            if targeted_context:
                contexts.append(targeted_context)
                facts_by_category = self._extract_requested_programme_facts(
                    context="\n".join(contexts),
                    programme=programme,
                    categories=categories,
                    language=language,
                )

        return facts_by_category

    def _format_application_timing_summary(self, programme: str, language: str) -> str:
        facts_by_category = self._get_application_timing_fact_values(programme, language)
        lines: list[str] = []

        start_values = facts_by_category.get("start") or []
        if start_values:
            label = "Start" if language == "de" else "Start"
            lines.append(
                f"- **{label}**: {self._format_requested_fact_values(start_values, 'start', language)}"
            )

        cost_values = facts_by_category.get("cost") or []
        if cost_values:
            label = "Gebühren" if language == "de" else "Tuition"
            lines.append(
                f"- **{label}**: {self._format_requested_fact_values(cost_values, 'cost', language)}"
            )

        deadline_values = facts_by_category.get("deadline") or []
        if deadline_values:
            label = "Bewerbungsfristen" if language == "de" else "Application deadlines"
            lines.append(
                f"- **{label}**: {self._format_requested_fact_values(deadline_values, 'deadline', language)}"
            )

        if not lines:
            return ""

        heading = "Aktuell relevant:" if language == "de" else "Currently relevant:"
        return f"{heading}\n" + "\n".join(lines)

    def _build_application_next_steps_response(self, language: str, programmes: list[str]) -> str:
        programme_labels = {
            "emba": ("EMBA HSG", "the admissions team"),
            "iemba": ("IEMBA HSG", "the admissions team"),
            "emba_x": ("emba X", "the admissions team"),
        }
        selected = [(p, *programme_labels[p]) for p in programmes if p in programme_labels]

        if len(selected) == 1:
            programme, programme_name, advisor = selected[0]
            facts = self._get_programme_facts(programme, language)
            timing_summary = self._format_application_timing_summary(programme, language)
            timing_block = f"\n\n{timing_summary}" if timing_summary else ""
            if language == "en":
                documents = self._format_fact_points(
                    facts.document_points,
                    "CV, degree certificates/transcripts, leadership scope, motivation, language readiness, and target start timing",
                ).rstrip(". ")
                return (
                    f"For the **{programme_name}** application, the next useful step is to prepare for an admissions "
                    f"conversation with **{advisor}**. Preparation: {documents}. In that conversation, admissions can "
                    f"confirm formal eligibility, documents, deadlines, and the best timing for submission.{timing_block}"
                )
            documents = self._format_fact_points(
                facts.document_points,
                "CV, Studienabschluss/Zeugnisse, Führungsverantwortung, Motivation, Sprachniveau und gewünschter Startzeitpunkt",
            ).rstrip(". ")
            return (
                f"Für die Bewerbung zum **{programme_name}** ist der nächste sinnvolle Schritt die Vorbereitung auf eine "
                f"Zulassungs- und Beratungsabklärung mit **{advisor}**. Als Vorbereitung relevant: {documents}. Dabei "
                f"können formaler Fit, Unterlagen, Fristen und der beste Zeitpunkt für die Einreichung geklärt werden.{timing_block}"
            )

        if language == "en":
            return (
                "For the application step, the important point is to clarify the right programme before submitting "
                "documents. Prepare your CV, degree certificates, leadership scope, motivation, language readiness, and "
                "preferred start timing. Because more than one Executive MBA option is still relevant, first narrow the "
                "target programme before submitting documents."
            )

        return (
            "Für den Bewerbungsschritt sollte zuerst geklärt werden, welches der drei Executive-MBA-Programme wirklich "
            "das richtige Ziel ist. Vorbereiten sollten Sie CV, Studienabschluss, Führungsverantwortung, Motivation, "
            "Sprachniveau und den gewünschten Startzeitpunkt. Da noch mehrere Programme relevant sind, sollte vor der "
            "Einreichung zuerst das Zielprogramm eingegrenzt werden."
        )

    def _serve_application_next_steps(
        self,
        processed_query: str,
        response_language: str,
        programmes: list[str],
    ) -> LeadAgentQueryResponse:
        chain_logger.info(f"Serving application next-step guidance for programmes: {programmes}")
        response = self._build_application_next_steps_response(response_language, programmes)
        response = ResponseFormatter.format_name_of_university(response, language=response_language)
        response = ResponseFormatter.clean_response(response)

        self._pending_continuation = None
        self._conversation_history.append(HumanMessage(processed_query))
        self._conversation_history.append(AIMessage(response))
        if len(programmes) == 1:
            self._conversation_state["suggested_program"] = programmes[0]

        return LeadAgentQueryResponse(
            response=response,
            language=response_language,
            confidence_fallback=False,
            should_cache=False,
            processed_query=processed_query,
        )

    def _build_application_process_details_response(self, language: str, programmes: list[str]) -> str:
        normalized_programmes = [p for p in programmes if p in {"emba", "iemba", "emba_x"}]
        if not normalized_programmes:
            normalized_programmes = ["emba", "iemba", "emba_x"]

        if len(normalized_programmes) == 1:
            programme = normalized_programmes[0]
            programme_name, _ = self._programme_label_and_advisor(programme)
            facts = self._get_programme_facts(programme, language)

            if language == "en":
                fit = self._format_fact_points(
                    facts.fit_points,
                    "formal requirements should be checked against the current admissions material",
                )
                documents = self._format_fact_points(
                    facts.document_points,
                    "CV, certificates, leadership scope, motivation, goals, and language readiness should be prepared and confirmed with admissions",
                )
                timing = self._format_fact_points(
                    facts.timing_points,
                    "current deadlines, start dates, tuition, and available seats are not clearly available in the programme material",
                )
                focus = self._format_fact_points(
                    facts.focus_points,
                    "the programme goal should be clarified against the current programme material",
                )
                return (
                    f"For the **{programme_name}** application process, the practical sequence is:\n\n"
                    f"1. **Fit check**: {fit}.\n"
                    f"2. **Prepare documents**: {documents}.\n"
                    f"3. **Plan timing and tuition**: {timing}.\n"
                    f"4. **Admissions conversation**: confirm formal eligibility, programme fit, goals, timing, current "
                    f"deadlines, and open questions. Programme goal: {focus}.\n"
                    "5. **Submit application and enrol**: admissions confirms the submission route, missing documents, "
                    "decision process, enrolment steps, and payment details."
                )

            fit = self._format_fact_points(
                facts.fit_points,
                "formale Anforderungen sollten anhand des aktuellen Zulassungsmaterials geprüft werden",
            )
            documents = self._format_fact_points(
                facts.document_points,
                "CV, Zeugnisse, Führungsverantwortung, Motivation, Ziele und Sprachniveau sollten vorbereitet und mit Admissions bestätigt werden",
            )
            timing = self._format_fact_points(
                facts.timing_points,
                "aktuelle Fristen, Startdaten, Gebühren und verfügbare Plätze sind in den Programmunterlagen gerade nicht eindeutig verfügbar",
            )
            focus = self._format_fact_points(
                facts.focus_points,
                "das Programmziel sollte anhand der aktuellen Programmunterlagen geklärt werden",
            )
            return (
                f"Für die Bewerbung zum **{programme_name}** läuft der Prozess praktisch so:\n\n"
                f"1. **Fit prüfen**: {fit}.\n"
                f"2. **Unterlagen vorbereiten**: {documents}.\n"
                f"3. **Timing und Gebühren planen**: {timing}.\n"
                f"4. **Zulassungs-/Beratungsgespräch**: formaler Fit, Programm-Fit, Ziele, Timing, aktuelle Fristen und "
                f"offene Fragen klären. Programmziel: {focus}.\n"
                "5. **Bewerbung einreichen und Einschreibung finalisieren**: Admissions bestätigt Einreichungsweg, "
                "fehlende Unterlagen, Entscheidungsprozess, Einschreibung und Zahlungs-/Gebührenthemen."
            )

        facts_by_programme = self._get_programmes_facts(normalized_programmes, language)
        summaries = [
            self._build_programme_fact_summary_from_facts(
                programme,
                language,
                facts_by_programme.get(programme, ProgrammeFacts(programme=programme)),
            )
            for programme in normalized_programmes
        ]
        joined_summaries = "\n".join(f"- {summary}" for summary in summaries)

        if language == "en":
            return (
                "Before applying, first decide which programme you want to target. The process then follows the same "
                "structure: fit check, documents, admissions conversation, "
                "application submission, decision, and enrolment.\n\n"
                f"{joined_summaries}\n\n"
                "For the conversation, prepare CV, degree certificates/transcripts, leadership overview, motivation, "
                "language readiness, and preferred timing. Exact current facts should be confirmed by admissions."
            )
        return (
            "Vor der Bewerbung sollte zuerst geklärt werden, welches Programm Sie konkret ansteuern. Danach ist der "
            "Ablauf grundsätzlich: Fit prüfen, Unterlagen vorbereiten, "
            "Zulassungs-/Beratungsgespräch, Bewerbung einreichen, Entscheid und Einschreibung.\n\n"
            f"{joined_summaries}\n\n"
            "Für das Gespräch sollten Sie CV, Studienabschluss/Zeugnisse, Führungsverantwortung, Motivation, Sprachniveau "
            "und gewünschten Startzeitpunkt vorbereiten. Konkrete aktuelle Angaben sollten durch Admissions bestätigt werden."
        )

    def _serve_application_process_details(
        self,
        processed_query: str,
        response_language: str,
        programmes: list[str],
    ) -> LeadAgentQueryResponse:
        chain_logger.info(f"Serving application process details for programmes: {programmes}")
        response = self._build_application_process_details_response(response_language, programmes)
        response = ResponseFormatter.format_name_of_university(response, language=response_language)
        response = ResponseFormatter.clean_response(response)

        self._pending_continuation = None
        self._conversation_history.append(HumanMessage(processed_query))
        self._conversation_history.append(AIMessage(response))

        return LeadAgentQueryResponse(
            response=response,
            language=response_language,
            confidence_fallback=False,
            should_cache=False,
            processed_query=processed_query,
        )
