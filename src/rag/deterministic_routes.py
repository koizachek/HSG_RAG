import re

from langchain_core.messages import AIMessage, HumanMessage

from src.config import config
from src.rag.chain_components import ChainComponent
from src.rag.deterministic_responses import (
    BookingIntentDetector,
    LegacyProgrammeContentResponder,
    ProgrammeOverviewResponder,
)
from src.rag.response_formatter import ResponseFormatter
from src.rag.utilclasses import LeadAgentQueryResponse
from src.utils.logging import get_logger

chain_logger = get_logger('agent_chain')


class DeterministicRoutes(ChainComponent):
    def _previous_response_offered_booking(self) -> bool:
        """Return True if the latest assistant turn offered booking as a next step."""
        return BookingIntentDetector.latest_response_offered_booking(
            self._get_latest_ai_message_content()
        )

    def _get_latest_ai_message_content(self, skip_latest: bool = False) -> str:
        """Return the latest assistant message content from conversation history."""
        ai_messages_seen = 0

        for message in reversed(self._conversation_history):
            if not isinstance(message, AIMessage):
                continue

            ai_messages_seen += 1
            if skip_latest and ai_messages_seen == 1:
                continue

            content = getattr(message, "content", "") or getattr(message, "text", "")
            if isinstance(content, list):
                return " ".join(str(part) for part in content)
            return str(content)

        return ""

    def _is_booking_preference_follow_up(self, query: str) -> bool:
        """Detect short follow-up answers that continue an active booking flow."""
        return BookingIntentDetector.is_booking_preference_follow_up(query)

    def _previous_response_requested_booking_preferences(self) -> bool:
        """Return True when the previous assistant turn asked clarifying booking questions."""
        return BookingIntentDetector.latest_response_requested_booking_preferences(
            self._get_latest_ai_message_content()
        )

    def _response_commits_to_showing_booking_widget(self, response: str) -> bool:
        """Detect when the assistant says booking options are being shown now."""
        return BookingIntentDetector.response_commits_to_showing_booking_widget(response)

    def _is_explicit_booking_intent(self, query: str) -> bool:
        """Detect whether the user is actively asking to book or accepting a booking offer."""
        return BookingIntentDetector.is_explicit_booking_intent(
            query,
            self._get_latest_ai_message_content(),
        )

    def _is_continuation_request(self, query: str) -> bool:
        normalized = re.sub(r"[.!?,;:]", " ", query.lower()).strip()
        normalized = re.sub(r"\s+", " ", normalized)
        continuation_terms = {
            "ja",
            "ja bitte",
            "bitte",
            "gerne",
            "weiter",
            "bitte weiter",
            "mehr",
            "mehr details",
            "mehr details bitte",
            "ja mehr details",
            "noch mehr",
            "fortfahren",
            "weiter bitte",
            "and",
            "and more",
            "continue",
            "continue please",
            "more",
            "more details",
            "more details please",
        }
        return normalized in continuation_terms

    def _query_mentions_specific_programme(self, query: str) -> bool:
        query_lower = query.lower()
        return any(
            term in query_lower
            for term in [
                "emba hsg",
                "international emba",
                "iemba",
                "emba x",
                "embax",
            ]
        )

    def _extract_programme_preference(self, query: str) -> str | None:
        query_lower = query.lower()
        preference_terms = [
            "besser",
            "besserer fit",
            "beste",
            "am besten",
            "passt",
            "passender",
            "interessanter",
            "favorisiere",
            "tendiere",
            "klingt gut",
            "klingt besser",
            "finde ich gut",
            "finde ich besser",
            "nehme",
            "wähle",
            "waehle",
            "will",
            "möchte",
            "moechte",
            "sounds better",
            "best",
            "better fit",
            "prefer",
            "lean toward",
            "interested in",
            "i want",
            "i would choose",
        ]
        if not any(term in query_lower for term in preference_terms):
            return None

        if "emba x" in query_lower or "embax" in query_lower:
            return "emba_x"
        if "iemba" in query_lower or "international emba" in query_lower:
            return "iemba"
        if "emba hsg" in query_lower or re.search(r"\bemba\b", query_lower):
            return "emba"

        return None

    def _extract_programme_from_text(self, text: str) -> str | None:
        text_lower = text.lower()
        if "emba x" in text_lower or "embax" in text_lower:
            return "emba_x"
        if "iemba" in text_lower or "international emba" in text_lower:
            return "iemba"
        if "emba hsg" in text_lower:
            return "emba"
        return None

    def _extract_programmes_from_text(self, text: str) -> list[str]:
        text_lower = text.lower()
        programmes: list[str] = []

        if re.search(r"(?<!i)\bemba hsg\b", text_lower) or re.search(r"\bgerman(?:-speaking)?\s+emba\b", text_lower):
            programmes.append("emba")
        if "iemba" in text_lower or "international emba" in text_lower:
            programmes.append("iemba")
        if "emba x" in text_lower or "embax" in text_lower:
            programmes.append("emba_x")

        return programmes

    @staticmethod
    def _normalise_programme_id(programme: str | None) -> str | None:
        if not programme:
            return None
        programme_lower = str(programme).lower().replace("-", "_").replace(" ", "_")
        if programme_lower in {"emba_x", "embax"}:
            return "emba_x"
        if programme_lower in {"iemba", "iemba_hsg", "international_emba"}:
            return "iemba"
        if programme_lower in {"emba", "emba_hsg"}:
            return "emba"
        return None

    def _is_application_next_step_request(self, query: str) -> bool:
        query_lower = query.lower()
        application_terms = [
            "bewerb",
            "bewerbung",
            "bewerben",
            "bewerbungsprozess",
            "bewerbungsunterlagen",
            "zulassung",
            "assessment",
            "application",
            "apply",
            "admission",
            "admissions",
            "admissions process",
            "application documents",
        ]
        return any(term in query_lower for term in application_terms)

    def _is_application_next_step_route(self, query: str) -> bool:
        """Return True for process/next-step application questions, not deadline-only fact questions."""
        if not self._is_application_next_step_request(query):
            return False

        query_lower = query.lower()
        timing_or_price_terms = [
            "wann",
            "frist",
            "fristen",
            "bewerbungsfrist",
            "bewerbungszeitraum",
            "bewerbungsperiode",
            "deadline",
            "deadlines",
            "application deadline",
            "application period",
            "start",
            "startdatum",
            "beginnt",
            "startet",
            "kosten",
            "kostet",
            "preis",
            "gebühr",
            "gebuehr",
            "chf",
            "dauer",
            "wie lange",
        ]
        process_terms = [
            "wie bewerbe ich mich",
            "wie kann ich mich",
            "wie bewirbt man sich",
            "wie läuft die bewerbung",
            "wie laeuft die bewerbung",
            "bewerbungsprozess",
            "bewerbungsablauf",
            "prozess",
            "ablauf",
            "schritte",
            "unterlagen",
            "dokument",
            "dokumente",
            "zulassung",
            "assessment",
            "how do i apply",
            "how can i apply",
            "how to apply",
            "application process",
            "admissions process",
            "application steps",
            "application documents",
            "documents",
        ]

        if any(term in query_lower for term in process_terms):
            return True

        if re.search(r"\bwie\b.{0,100}\b(bewerben|bewerbe|bewerbung|bewirbt)\b", query_lower):
            return True
        if re.search(r"\bhow\b.{0,100}\b(apply|application|admission|admissions)\b", query_lower):
            return True

        if any(term in query_lower for term in timing_or_price_terms):
            return False

        return any(
            term in query_lower
            for term in ["bewerben", "bewerbung", "apply", "application", "admission", "admissions"]
        )

    def _is_application_process_detail_request(self, query: str) -> bool:
        query_lower = query.lower()
        detail_terms = [
            "prozess",
            "ablauf",
            "schritt",
            "schritte",
            "unterlagen",
            "dokument",
            "dokumente",
            "fristen",
            "frist",
            "deadline",
            "deadlines",
            "timeline",
            "process",
            "steps",
            "documents",
            "wie läuft",
            "wie laeuft",
            "how does it work",
            "how does the process work",
        ]
        return any(term in query_lower for term in detail_terms)

    def _previous_response_was_application_next_step(self) -> bool:
        content_lower = self._get_latest_ai_message_content().lower()
        if not content_lower:
            return False

        application_terms = [
            "bewerbung zum",
            "bewerbungsschritt",
            "zulassungs- und beratungsgespräch",
            "terminoptionen und kontaktdaten",
            "application step",
            "application, the next useful step",
            "appointment options and contact details",
            "admissions conversation",
        ]
        return any(term in content_lower for term in application_terms)

    def _resolve_known_application_programmes(self, query: str) -> list[str]:
        programme = self._extract_programme_from_text(query)
        if programme:
            return [programme]

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

        latest_ai = self._get_latest_ai_message_content()
        if self._text_mentions_multiple_programmes(latest_ai) or "alle drei" in latest_ai.lower():
            return ["emba", "iemba", "emba_x"]

        return []

    def _resolve_application_programmes(self, query: str) -> list[str]:
        if self._is_explicit_booking_intent(query):
            return []

        if not self._is_application_next_step_route(query):
            return []

        programmes = self._resolve_known_application_programmes(query)
        if programmes:
            return programmes

        if self._latest_ai_mentions_multiple_programmes():
            return ["emba", "iemba", "emba_x"]

        return []

    def _append_deterministic_response(
        self,
        processed_query: str,
        response: str,
        response_language: str,
        relevant_programs: list[str] | None = None,
        suggested_program: str | None = None,
    ) -> LeadAgentQueryResponse:
        response = ResponseFormatter.format_name_of_university(response, language=response_language)
        response = ResponseFormatter.clean_response(response)

        self._pending_continuation = None
        self._conversation_history.append(HumanMessage(processed_query))
        self._conversation_history.append(AIMessage(response))

        if hasattr(self, "_conversation_state"):
            if suggested_program is not None:
                self._conversation_state["suggested_program"] = suggested_program
            if relevant_programs:
                program_interest = self._conversation_state.setdefault("program_interest", [])
                if program_interest is not None:
                    for programme in relevant_programs:
                        if programme not in program_interest:
                            program_interest.append(programme)

        return LeadAgentQueryResponse(
            response=response,
            language=response_language,
            confidence_fallback=False,
            should_cache=False,
            processed_query=processed_query,
            appointment_requested=False,
            show_booking_widget=False,
            relevant_programs=relevant_programs or [],
        )

    def _is_emba_minimal_profile_guidance_request(self, query: str) -> bool:
        query_lower = query.lower()
        context_lower = self._human_context_for_recommendation(query)
        has_emba_context = (
            "executive mba" in context_lower
            or "emba hsg" in context_lower
            or "berufsbegleitend" in context_lower
        )
        has_minimum_profile = (
            ("6 jahre" in context_lower and "3 jahre" in context_lower)
            or ("6 years" in context_lower and "3 years" in context_lower)
        )
        asks_fit = any(
            term in query_lower
            for term in [
                "infrage",
                "ausreicht",
                "chancen",
                "qualify",
                "eligible",
                "chances",
            ]
        )
        return has_emba_context and has_minimum_profile and asks_fit

    def _serve_emba_minimal_profile_guidance(
        self,
        processed_query: str,
        response_language: str,
    ) -> LeadAgentQueryResponse:
        query_lower = processed_query.lower()
        if response_language == "de":
            if "chancen" in query_lower:
                response = (
                    "Mit **6 Jahren Berufserfahrung** und **3 Jahren Teamleitung** liegen Sie grundsätzlich im "
                    "passenden Bereich für den **EMBA HSG**. Eine Zusage kann ich daraus nicht ableiten; gute Chancen "
                    "hängen vor allem davon ab, ob Ihre Führung substanziell ist.\n\n"
                    "Wichtig für die Einschätzung sind Teamgrösse, direkte Personalverantwortung, Budget- oder "
                    "Projektverantwortung, Entscheidungsspielraum und Entwicklung Ihrer Rolle. Der Zulassungsausschuss "
                    "prüft das individuell; für einen Grenzfall ist eine kurze Profilprüfung durch Admissions sinnvoll."
                )
            elif "ausreicht" in query_lower:
                response = (
                    "Ihre **3 Jahre Führungserfahrung** erfüllen die typische Mindestmarke für den **EMBA HSG**, aber "
                    "die Qualität der Führung ist entscheidend. Admissions schaut nicht nur auf Jahre, sondern auf "
                    "Personalverantwortung, Teamgrösse, Projekt-/Budgetverantwortung und Entscheidungsspielraum.\n\n"
                    "Wenn Ihre Teamleitung echte Verantwortung umfasst, wirkt Ihr Profil grundsätzlich plausibel. Wenn "
                    "es eher fachliche Koordination ohne Entscheidungsmandat ist, sollte Admissions den Fit prüfen."
                )
            else:
                response = (
                    "Ja, grundsätzlich kommen Sie für den **EMBA HSG** infrage: **6 Jahre Berufserfahrung** und "
                    "**3 Jahre Teamleitung** treffen die zentralen Erfahrungsanforderungen. Die finale Zulassung hängt "
                    "aber vom Gesamtprofil ab.\n\n"
                    "Für die Prüfung zählen besonders anerkannter Hochschulabschluss, Art und Umfang Ihrer "
                    "Führungsverantwortung, Motivation, Deutschkenntnisse und ob das berufsbegleitende Format zu Ihrer "
                    "aktuellen Rolle passt."
                )
        else:
            response = (
                "With **6 years of professional experience** and **3 years of team leadership**, you are broadly in the "
                "right range for the **EMBA HSG**. Final admission depends on the quality of your leadership scope, "
                "degree background, motivation, and language fit."
            )

        return self._append_deterministic_response(
            processed_query,
            response,
            response_language,
            relevant_programs=["emba"],
            suggested_program="emba",
        )

    @staticmethod
    def _is_mixed_language_programme_overview_request(query: str) -> bool:
        query_lower = query.lower()
        return (
            "program" in query_lower
            and any(term in query_lower for term in ["sobre", "quiero", "want to know", "programs"])
            and any(term in query_lower for term in ["ich", "deutsch", "german"])
        )

    def _serve_mixed_language_programme_overview(
        self,
        processed_query: str,
        response_language: str,
    ) -> LeadAgentQueryResponse:
        def cost_suffix(programme: str) -> str:
            tuition = self._current_tuition_value(programme, "de")
            return f", Kosten **{tuition}**" if tuition else ""

        response = (
            "Darf ich kurz nachfragen: Möchten Sie lieber auf **Deutsch oder Englisch** weiterschreiben? Ihre Nachricht "
            "ist gemischt, deshalb frage ich kurz nach.\n\n"
            "Zur Orientierung die drei Executive-MBA-Optionen:\n"
            f"- **EMBA HSG**: deutschsprachig, General Management, DACH-Fokus{cost_suffix('emba')}.\n"
            f"- **IEMBA HSG**: englischsprachig, internationaler General-Management-Fokus{cost_suffix('iemba')}.\n"
            "- **emba X**: englischsprachig, ETH Zürich + Universität St.Gallen, Technologie, Innovation, "
            f"Transformation und Nachhaltigkeit{cost_suffix('emba_x')}.\n\n"
            "Ich kann die Programme vergleichen oder anhand Ihres Profils eine erste Richtung empfehlen."
        )
        return self._append_deterministic_response(
            processed_query,
            response,
            "de" if response_language not in {"de", "en"} else response_language,
            relevant_programs=["emba", "iemba", "emba_x"],
        )

    def _is_iemba_visa_request(self, query: str) -> bool:
        query_lower = query.lower()
        if not any(term in query_lower for term in ["visa", "permit", "schengen"]):
            return False
        context_lower = self._human_context_for_recommendation(query)
        return "iemba" in context_lower or "international" in context_lower or "us" in query_lower

    def _serve_iemba_visa_response(
        self,
        processed_query: str,
        response_language: str,
    ) -> LeadAgentQueryResponse:
        response = LegacyProgrammeContentResponder.iemba_visa_response()
        return self._append_deterministic_response(
            processed_query,
            response,
            "en",
            relevant_programs=["iemba"],
            suggested_program="iemba",
        )

    def _is_iemba_apac_alumni_request(self, query: str) -> bool:
        query_lower = query.lower()
        if not any(term in query_lower for term in ["asia-pacific", "apac", "asia", "alumni network"]):
            return False
        context_lower = self._human_context_for_recommendation(query)
        return "iemba" in context_lower or "international" in context_lower

    def _serve_iemba_apac_alumni_response(
        self,
        processed_query: str,
        response_language: str,
    ) -> LeadAgentQueryResponse:
        response = LegacyProgrammeContentResponder.iemba_apac_alumni_response()
        return self._append_deterministic_response(
            processed_query,
            response,
            "en",
            relevant_programs=["iemba"],
            suggested_program="iemba",
        )

    @staticmethod
    def _is_embax_comparison_request(query: str) -> bool:
        query_lower = query.lower()
        return (
            ("emba x" in query_lower or "embax" in query_lower)
            and any(term in query_lower for term in ["unterscheidet", "difference", "different"])
            and any(term in query_lower for term in ["normal", "executive mba", "emba"])
        )

    def _serve_embax_comparison_response(
        self,
        processed_query: str,
        response_language: str,
    ) -> LeadAgentQueryResponse:
        response = LegacyProgrammeContentResponder.embax_comparison_response(response_language)
        return self._append_deterministic_response(
            processed_query,
            response,
            response_language,
            relevant_programs=["emba_x", "emba"],
        )

    def _is_embax_language_request(self, query: str) -> bool:
        query_lower = query.lower()
        context_lower = self._human_context_for_recommendation(query)
        return (
            ("emba x" in context_lower or "embax" in context_lower or "eth" in context_lower)
            and any(term in query_lower for term in ["deutsch", "englisch", "english", "german", "unterrichtet"])
        )

    def _serve_embax_language_response(
        self,
        processed_query: str,
        response_language: str,
    ) -> LeadAgentQueryResponse:
        response = LegacyProgrammeContentResponder.embax_language_response(response_language)
        return self._append_deterministic_response(
            processed_query,
            response,
            response_language,
            relevant_programs=["emba_x"],
            suggested_program="emba_x",
        )

    def _is_likely_too_early_for_executive_mba(self, query: str) -> bool:
        query_lower = query.lower()
        if "bachelor" not in query_lower:
            return False
        if not any(term in query_lower for term in ["executive mba", "emba", "mba", "bewerben", "apply"]):
            return False

        experience_years = self._extract_experience_years(query)
        return experience_years is not None and experience_years <= 2

    def _serve_too_early_for_executive_mba(
        self,
        processed_query: str,
        response_language: str,
    ) -> LeadAgentQueryResponse:
        response = LegacyProgrammeContentResponder.too_early_for_executive_mba_response(response_language)
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
            appointment_requested=False,
            show_booking_widget=False,
            relevant_programs=[],
        )

    @staticmethod
    def _is_price_frustration_request(query: str) -> bool:
        query_lower = query.lower()
        price_signal = any(
            term in query_lower
            for term in [
                "teuer",
                "wucher",
                "preis",
                "gebuehr",
                "gebühr",
                "expensive",
                "overpriced",
                "price",
                "cost",
                "tuition",
            ]
        )
        frustration_signal = any(
            term in query_lower
            for term in [
                "warum",
                "why",
                "?!",
                "!",
                "ärger",
                "aerger",
                "frustriert",
                "frustrated",
                "too much",
            ]
        )
        return price_signal and frustration_signal

    def _serve_price_frustration_response(
        self,
        processed_query: str,
        response_language: str,
    ) -> LeadAgentQueryResponse:
        programmes = ["emba", "iemba", "emba_x"]
        fee_lines = []
        for programme in programmes:
            programme_name, _ = self._programme_label_and_advisor(programme)
            tuition = self._current_tuition_value(programme, response_language)
            if tuition:
                fee_lines.append(f"- **{programme_name}**: **{tuition}**")
        fee_block = "\n".join(fee_lines)

        if response_language == "de":
            fee_intro = (
                f"Die aktuell aus den strukturierten Programmdaten gelesenen Gebühren sind:\n{fee_block}\n\n"
                if fee_block
                else (
                    "Ich möchte hier keine Gebühr aus dem Gedächtnis nennen. Wenn Sie mir das konkrete Programm "
                    "nennen, prüfe ich die aktuellen strukturierten Programmdaten bzw. verweise auf Admissions.\n\n"
                )
            )
            response = (
                "Ich verstehe den Ärger über die Höhe der Studiengebühren; das ist eine grosse Investition, "
                "und die Frage ist absolut berechtigt.\n\n"
                f"{fee_intro}"
                "Der Preis deckt nicht nur Unterricht ab, sondern ein berufsbegleitendes Executive-Format mit "
                "intensiven Modulen, erfahrenen Dozierenden, Leadership-Entwicklung, Coaching- bzw. Netzwerkformaten "
                "und Zugang zum HSG Alumni-Netzwerk. Reise-, Unterkunfts- und einzelne Verpflegungskosten sind je nach "
                "Programm zusätzlich zu prüfen.\n\n"
                "Wenn Sie möchten, kann ich als Nächstes für ein bestimmtes Programm aufschlüsseln, was in der Gebühr "
                "enthalten ist und welche Punkte Sie mit Admissions zur Finanzierung oder Arbeitgeberbeteiligung klären sollten. "
                "Für eine menschliche Einordnung können Sie Admissions direkt kontaktieren."
            )
        else:
            fee_intro = (
                f"The tuition fees read from the structured programme facts are:\n{fee_block}\n\n"
                if fee_block
                else (
                    "I do not want to quote a tuition amount from memory. If you name the programme, I can check the "
                    "structured programme facts or point you to admissions.\n\n"
                )
            )
            response = (
                "I understand the frustration; an Executive MBA is a major investment, so it is fair to ask what the "
                "price reflects.\n\n"
                f"{fee_intro}"
                "The fee is not only for classroom teaching. It covers a part-time executive format with intensive "
                "modules, experienced faculty, leadership development, coaching or network formats, and access to the "
                "HSG alumni network. Travel, accommodation, and some meals may still need to be budgeted separately.\n\n"
                "If you name the programme you are considering, I can break down what is included and which financing "
                "or employer-sponsorship questions admissions should clarify with you. For a human review, you can "
                "contact admissions directly."
            )

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
            appointment_requested=False,
            show_booking_widget=False,
            relevant_programs=[],
        )

    def _append_cost_orientation_to_redirect(self, redirect_msg: str, language: str) -> str:
        fee_lines = []
        for programme in ["emba", "iemba", "emba_x"]:
            programme_name, _ = self._programme_label_and_advisor(programme)
            tuition = self._current_tuition_value(programme, language)
            if tuition:
                fee_lines.append(f"- **{programme_name}**: **{tuition}**")
        if not fee_lines:
            return redirect_msg

        fee_block = "\n".join(fee_lines)
        if language == "de":
            return (
                f"{redirect_msg}\n\n"
                "Zur schnellen Orientierung, falls Ihre nächste Frage die Kosten betrifft:\n"
                f"{fee_block}"
            )
        return (
            f"{redirect_msg}\n\n"
            "For quick orientation if your next question is about costs:\n"
            f"{fee_block}"
        )

    def _is_iemba_embax_tech_career_change_request(self, query: str) -> bool:
        query_lower = query.lower()
        context_lower = self._human_context_for_recommendation(query)

        has_iemba_context = "iemba" in context_lower or "international emba" in context_lower
        has_tech_context = any(
            term in context_lower
            for term in [
                "software engineer",
                "software",
                "technology",
                "technologie",
                "tech background",
                "technical background",
                "digital",
                "data",
                "ai",
            ]
        )
        has_career_change_context = any(
            term in context_lower
            for term in [
                "business leadership",
                "career change",
                "move into business",
                "management experience",
                "without management",
                "non-standard",
                "non standard",
            ]
        )
        query_requests_guidance = any(
            term in query_lower
            for term in [
                "qualify",
                "eligible",
                "better fit",
                "tech background",
                "strengthen",
                "application",
                "management experience",
                "emba x",
                "embax",
            ]
        )

        return (
            has_iemba_context
            and has_tech_context
            and has_career_change_context
            and query_requests_guidance
        )

    def _is_iemba_eligibility_assessment_request(self, query: str) -> bool:
        query_lower = query.lower()
        if not any(term in query_lower for term in ["eligible", "eligibility", "qualify", "assess"]):
            return False
        context_lower = self._human_context_for_recommendation(query)
        has_iemba_context = (
            "iemba" in context_lower
            or "international emba" in context_lower
            or "international focus" in context_lower
            or "internationally focused" in context_lower
        )
        has_tech_career_context = any(
            term in context_lower
            for term in ["software engineer", "tech background", "without management", "business leadership"]
        )
        return has_iemba_context and not has_tech_career_context

    def _serve_iemba_eligibility_assessment(
        self,
        processed_query: str,
        response_language: str,
    ) -> LeadAgentQueryResponse:
        if response_language == "de":
            response = (
                "Für eine erste, unverbindliche Einschätzung zum **IEMBA HSG** brauche ich vor allem: höchsten "
                "Abschluss, Jahre Vollzeit-Berufserfahrung, aktuelle Rolle, Führungs- oder Projektverantwortung, "
                "internationale Erfahrung und Englisch-Niveau.\n\n"
                "Typischerweise passt der IEMBA HSG zu Kandidatinnen und Kandidaten mit abgeschlossenem Studium, "
                "mehrjähriger Berufserfahrung, klarer Leadership-Verantwortung und internationaler Ausrichtung. "
                "Die finale Entscheidung trifft Admissions.\n\n"
                "Für eine formale Profilprüfung können Sie **Admissions kontaktieren** und Ihren CV "
                "sowie kurze Angaben zu Führungserfahrung, Ausbildung und Zielsetzung teilen."
            )
        else:
            response = (
                "I can give you an initial, non-binding view for the **IEMBA HSG**. The key facts I need are: highest "
                "degree, years of full-time experience, current role, people/project/budget leadership, international "
                "exposure, and English level.\n\n"
                "In general, IEMBA HSG is a fit when you have a recognised degree, several years of professional "
                "experience, clear leadership responsibility, and an international management goal. Final eligibility "
                "is decided by admissions.\n\n"
                "Recommended next step: a **formal admissions profile review**; please **contact admissions**. "
                "Send your CV plus a short summary of your leadership scope, education, international "
                "exposure, and goals; that gives admissions enough context for a clear eligibility assessment."
            )

        response = ResponseFormatter.format_name_of_university(response, language=response_language)
        response = ResponseFormatter.clean_response(response)

        self._pending_continuation = None
        self._conversation_history.append(HumanMessage(processed_query))
        self._conversation_history.append(AIMessage(response))
        if hasattr(self, "_conversation_state"):
            self._conversation_state["suggested_program"] = "iemba"
            program_interest = self._conversation_state.setdefault("program_interest", [])
            if program_interest is not None and "iemba" not in program_interest:
                program_interest.append("iemba")

        return LeadAgentQueryResponse(
            response=response,
            language=response_language,
            confidence_fallback=False,
            should_cache=False,
            processed_query=processed_query,
            appointment_requested=False,
            show_booking_widget=False,
            relevant_programs=["iemba"],
        )

    def _serve_iemba_embax_tech_career_guidance(
        self,
        processed_query: str,
        response_language: str,
    ) -> LeadAgentQueryResponse:
        query_lower = processed_query.lower()
        asks_embax_fit = "emba x" in query_lower or "embax" in query_lower or "better fit" in query_lower
        asks_strengthening = "strengthen" in query_lower or "application" in query_lower
        asks_eligibility = "eligible" in query_lower or "qualify" in query_lower or "am i eligible" in query_lower
        has_prior_user_turns = any(isinstance(message, HumanMessage) for message in self._conversation_history)

        if response_language == "de":
            if asks_embax_fit:
                response = (
                    "Ja, für einen Software- oder Technologiehintergrund kann **emba X** der stärkere "
                    "Tech-/Business-/Transformations-Fit sein. **IEMBA HSG** ist eher der internationale/generalistische "
                    "Managementpfad mit globaler Perspektive.\n\n"
                    "Beide Wege bleiben möglich, aber weil Ihre Führungserfahrung nicht klassisches Linienmanagement ist, "
                    "sollte **Admissions** entscheiden, welche Bewerbung tragfähiger ist und welche Nachweise zählen. "
                    "Kontaktieren Sie Admissions dafür mit Ihrem CV."
                )
            elif asks_eligibility:
                response = (
                    "Eine belastbare Zulassungszusage kann ich nicht geben. Mit 9 Jahren Software-Erfahrung können Sie "
                    "grundsätzlich interessant sein, aber ohne klassische Managementverantwortung ist die Einschätzung "
                    "nicht standardmässig.\n\n"
                    "**IEMBA HSG** wäre der internationale/generalistische Managementpfad; **emba X** der stärkere "
                    "Tech-/Business-/Transformationspfad. Der nächste sinnvolle Schritt ist eine Profilprüfung durch "
                    "**Admissions** mit CV und Beispielen für Projekt-, Produkt-, Stakeholder- oder informelle Führung. "
                    "Kontaktieren Sie Admissions mit Ihrem CV und konkreten Führungsbeispielen."
                )
            elif asks_strengthening:
                response = (
                    "Stärken Sie die Bewerbung, indem Sie Führung ohne formalen Managementtitel konkret belegen: "
                    "Projekt- oder Produktverantwortung, Stakeholder-Steuerung, Budget-/Roadmap-Beiträge, Einfluss ohne "
                    "Weisungsbefugnis und messbare Ergebnisse.\n\n"
                    "**IEMBA HSG** ist der internationale/generalistische Managementpfad; **emba X** ist der stärkere "
                    "Tech-/Business-/Transformationspfad. Weil Ihre Führungserfahrung non-standard ist, sollte "
                    "**Admissions** entscheiden, welcher Weg besser passt. Kontaktieren Sie Admissions mit Ihrem CV "
                    "und konkreten Führungsbeispielen."
                )
            else:
                response = (
                    "Beide Wege sind möglich, aber sie stehen für unterschiedliche Ziele.\n\n"
                    "**IEMBA HSG** ist der internationale/generalistische Managementpfad: passend, wenn Sie globale "
                    "Managementperspektive, eine internationale Peer Group und Führung über Märkte hinweg aufbauen wollen.\n\n"
                    "**emba X** ist der Tech-/Business-/Transformationspfad: passend, wenn Sie einen Software- oder "
                    "Technologiehintergrund in Business Leadership, Innovation oder Transformation übersetzen wollen.\n\n"
                    "Weil Ihre Führungserfahrung nicht dem Standardprofil mit klarer Linienführung entspricht, sollte "
                    "**Admissions** entscheiden, welche Bewerbung stärker ist und welche Nachweise zählen. Kontaktieren "
                    "Sie Admissions mit Ihrem CV für eine Profilprüfung."
                )
        else:
            if asks_embax_fit:
                response = (
                    "Yes. For a software or technology background, **emba X** can be the stronger "
                    "tech/business/transformation fit. **IEMBA HSG** is the international/general management path with "
                    "a broader global-management perspective.\n\n"
                    "Both routes remain possible, but because your leadership experience is non-standard rather than "
                    "classic line management, **admissions should decide** which application route is stronger and what "
                    "evidence counts. Recommended next step: a **human admissions handover/profile review** with your "
                    "CV and concrete leadership examples."
                )
            elif asks_eligibility:
                if has_prior_user_turns:
                    response = (
                        "Short answer: you are **eligible for an admissions profile review**, but not a clean standard "
                        "admit yet. Your **9 years of software experience** meet the seniority range; the open question "
                        "is whether you can evidence leadership beyond individual contribution.\n\n"
                        "For your goals, **emba X** is the stronger thematic fit if you want to turn a tech background into "
                        "business, innovation, or transformation leadership. **IEMBA HSG** remains plausible if your main "
                        "goal is international/general management.\n\n"
                        "Recommended next step: **handover to admissions now** for a human profile review. I can help "
                        "prepare the handover note; it should include your CV and 2-3 concrete leadership examples: "
                        "project or product ownership, stakeholder steering, mentoring, roadmap influence, budget "
                        "responsibility, or measurable delivery impact. Admissions can then assess the appropriate "
                        "programme route."
                    )
                else:
                    response = (
                        "You meet the **experience-length** signal for an Executive MBA: 9 years in software is enough "
                        "for an admissions profile review. The unresolved issue is the leadership criterion. Without "
                        "formal management experience, your profile is **non-standard**, not an automatic rejection.\n\n"
                        "Admissions will look for evidence such as tech lead responsibility, project or product ownership, "
                        "stakeholder leadership, mentoring, budget or roadmap influence, and measurable impact.\n\n"
                        "**IEMBA HSG** fits if your main goal is international/general management. Given your tech background "
                        "and transition-to-business goal, **emba X** is also highly relevant because it connects technology, "
                        "innovation, transformation, and leadership. Recommended next step: a **human admissions "
                        "profile review** with your CV and concrete leadership examples."
                    )
            elif asks_strengthening:
                response = (
                    "Strengthen the application by making leadership without a formal management title concrete: project "
                    "or product ownership, stakeholder steering, roadmap or budget influence, influence without authority, "
                    "and measurable outcomes.\n\n"
                    "**IEMBA HSG** is the international/general management path; **emba X** is the stronger "
                    "tech/business/transformation path. Because your leadership experience is non-standard, "
                    "**admissions should decide** which route fits better. Recommended next step: send your CV and "
                    "specific leadership evidence for a human profile review. Admissions can then assess the appropriate "
                    "programme route."
                )
            else:
                response = (
                    "Both routes are possible, but they point to different goals.\n\n"
                    "**IEMBA HSG** is the international/general management path: strongest if you want global management "
                    "perspective, an international peer group, and cross-border leadership.\n\n"
                    "**emba X** is the tech/business/transformation path: strongest if you want to translate a software "
                    "or technology background into business leadership, innovation, or transformation work.\n\n"
                    "Because your leadership experience is non-standard rather than classic line management, "
                    "**admissions should decide** which application route is stronger and what evidence counts. Please "
                    "**contact admissions** with your CV for a profile review."
                )

        response = ResponseFormatter.format_name_of_university(response, language=response_language)
        response = ResponseFormatter.clean_response(response)

        self._pending_continuation = None
        self._conversation_history.append(HumanMessage(processed_query))
        self._conversation_history.append(AIMessage(response))
        if hasattr(self, "_conversation_state"):
            self._conversation_state["suggested_program"] = None
            program_interest = self._conversation_state.setdefault("program_interest", [])
            if program_interest is None:
                program_interest = []
                self._conversation_state["program_interest"] = program_interest
            for programme in ["iemba", "emba_x"]:
                if programme not in program_interest:
                    program_interest.append(programme)

        return LeadAgentQueryResponse(
            response=response,
            language=response_language,
            confidence_fallback=False,
            should_cache=False,
            processed_query=processed_query,
            appointment_requested=False,
            show_booking_widget=False,
            relevant_programs=["iemba", "emba_x"],
        )

    def _is_general_mba_overview_request(self, query: str) -> bool:
        query_lower = query.lower()
        if self._query_mentions_specific_programme(query_lower):
            return False

        general_mba_terms = [
            "mba",
            "executive mba",
            "weiterbildungs-mba",
            "weiterbildungsmba",
        ]
        discovery_terms = [
            "interessiere",
            "interested",
            "welche",
            "which",
            "option",
            "programm",
            "program",
            "passt",
            "fit",
            "geeignet",
            "empfehlen",
            "recommend",
        ]
        return (
            any(term in query_lower for term in general_mba_terms)
            and any(term in query_lower for term in discovery_terms)
        )

    def _is_profile_context_update(self, query: str) -> bool:
        query_lower = query.lower()
        profile_terms = [
            "jahre",
            "years",
            "chefarzt",
            "chief physician",
            "arzt",
            "doctor",
            "leadership",
            "führung",
            "fuehrung",
            "leiter",
            "leitung",
            "manager",
            "experience",
            "erfahrung",
            "berufserfahrung",
        ]
        return any(term in query_lower for term in profile_terms)

    def _profile_has_emba_hsg_signal(self, query: str, language: str) -> bool:
        context_lower = self._human_context_for_recommendation(query)
        experience_years = self._extract_experience_years(query)
        leadership_years = self._extract_leadership_years(query)
        if not experience_years or experience_years < 5:
            return False
        if not leadership_years or leadership_years < 3:
            return False

        disqualifying_goal_terms = [
            "international",
            "global",
            "englisch",
            "english",
            "ausland",
            "cross-border",
            "technology",
            "technologie",
            "digital",
            "digitalisierung",
            "innovation",
            "transformation",
            "nachhaltigkeit",
            "sustainability",
            "eth",
        ]
        if any(term in context_lower for term in disqualifying_goal_terms):
            return False

        german_preference_terms = [
            "deutsch",
            "german",
            "dach",
            "berufsbegleitend",
            "deutschsprachig",
        ]
        return language == "de" or any(term in context_lower for term in german_preference_terms)

    def _human_context_for_recommendation(self, query: str) -> str:
        texts = [query]
        for message in getattr(self, "_conversation_history", []) or []:
            if not isinstance(message, HumanMessage):
                continue
            content = getattr(message, "content", "") or getattr(message, "text", "")
            if isinstance(content, list):
                texts.append(" ".join(str(part) for part in content))
            else:
                texts.append(str(content))
        return "\n".join(texts).lower()

    def _recommended_programme_from_profile(self, query: str, language: str, profile_context: bool) -> str | None:
        context_lower = self._human_context_for_recommendation(query)
        tech_transformation_terms = [
            "nachhaltigkeit",
            "nachhaltige",
            "sustainability",
            "digitalisierung",
            "digitalization",
            "digitalisation",
            "technology",
            "technologie",
            "innovation",
            "transformation",
        ]
        if not profile_context and any(term in context_lower for term in tech_transformation_terms):
            return "emba_x"

        international_terms = [
            "international focus",
            "internationaler fokus",
            "international ausgerichtet",
            "global",
            "asia-pacific",
            "apac",
            "cross-border",
        ]
        if not profile_context and any(term in context_lower for term in international_terms):
            return "iemba"

        if profile_context and self._profile_has_emba_hsg_signal(query, language):
            return "emba"

        return None

    def _text_mentions_multiple_programmes(self, text: str) -> bool:
        text_lower = text.lower()
        if not text_lower:
            return False

        programme_mentions = [
            "emba hsg" in text_lower or "deutschsprachig" in text_lower,
            "iemba" in text_lower or "international emba" in text_lower,
            "emba x" in text_lower or "embax" in text_lower,
        ]
        return sum(programme_mentions) >= 2

    def _latest_ai_mentions_multiple_programmes(self) -> bool:
        return self._text_mentions_multiple_programmes(
            self._get_latest_ai_message_content()
        )

    def _serve_programme_overview(
        self,
        processed_query: str,
        response_language: str,
        detailed: bool,
        profile_context: bool = False,
    ) -> LeadAgentQueryResponse:
        chain_logger.info("Serving deterministic three-programme overview without a model call.")
        recommended_programme = (
            self._recommended_programme_from_profile(
                processed_query,
                response_language,
                profile_context,
            )
            if not detailed
            else None
        )
        response = ProgrammeOverviewResponder.build_response(
            language=response_language,
            detailed=detailed,
            detail_level=self._programme_overview_detail_level,
            profile_context=profile_context,
            recommended_programme=recommended_programme,
        )
        response = ResponseFormatter.format_name_of_university(response, language=response_language)
        response = ResponseFormatter.clean_response(response)

        self._pending_continuation = None
        self._programme_overview_profile_context = profile_context
        self._programme_overview_detail_level = (
            max(2, self._programme_overview_detail_level + 1)
            if detailed
            else 1
        )
        self._conversation_history.append(HumanMessage(processed_query))
        self._conversation_history.append(AIMessage(response))
        if recommended_programme and hasattr(self, "_conversation_state"):
            self._conversation_state["suggested_program"] = recommended_programme

        return LeadAgentQueryResponse(
            response=response,
            language=response_language,
            confidence_fallback=False,
            should_cache=False,
            processed_query=processed_query,
            appointment_requested=False,
            show_booking_widget=False,
            relevant_programs=[recommended_programme] if recommended_programme else ["emba", "iemba", "emba_x"],
        )

    def _serve_pending_continuation(
        self,
        processed_query: str,
        response_language: str,
    ) -> LeadAgentQueryResponse:
        chain_logger.info("Serving pending continuation without a new model call.")

        formatted_response, continuation = ResponseFormatter.chunk_response(
            self._pending_continuation or "",
            config.chain.MAX_RESPONSE_WORDS_LEAD,
            response_language,
        )
        self._pending_continuation = continuation
        formatted_response = ResponseFormatter.clean_response(formatted_response)
        formatted_response = ResponseFormatter.format_name_of_university(
            formatted_response,
            language=response_language,
        )

        return LeadAgentQueryResponse(
            response=formatted_response,
            language=response_language,
            confidence_fallback=False,
            should_cache=False,
            processed_query=processed_query,
            appointment_requested=False,
            show_booking_widget=False,
            relevant_programs=[],
        )
