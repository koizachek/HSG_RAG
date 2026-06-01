"""Deterministic helpers for the chatbot pipeline.

Control helpers are active only when configured. Legacy deterministic content
builders live here so agent_chain.py does not carry response constants; those
programme-content paths remain disabled by policy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.config import config


@dataclass(frozen=True)
class DeterministicResponsePolicy:
    """Configuration-backed switch for deterministic response paths."""

    control_enabled: bool = False
    programme_content_enabled: bool = False

    @classmethod
    def from_config(cls) -> "DeterministicResponsePolicy":
        control_enabled = bool(getattr(config.chain, "USE_DETERMINISTIC_RESPONSES", False))
        return cls(
            control_enabled=control_enabled,
            # Programme-content answer shortcuts are intentionally not exposed.
            # Weaviate retrieval and the LLM remain the fachliche answer path.
            programme_content_enabled=False,
        )


class BookingIntentDetector:
    """Detect booking state transitions without embedding programme content."""

    BOOKING_OFFER_TERMS = (
        "appointment slots",
        "book an appointment",
        "book a consultation",
        "appointment booking",
        "show you available appointments",
        "show appointment options",
        "terminbuchung",
        "termin buchen",
        "termine anzeigen",
        "verfuegbare termine",
        "verfügbare termine",
        "beratungstermin",
    )

    BOOKING_PREFERENCE_TERMS = (
        "online",
        "on-site",
        "onsite",
        "in person",
        "in-person",
        "st.gallen",
        "st. gallen",
        "morning",
        "mornings",
        "afternoon",
        "afternoons",
        "evening",
        "beginning of the week",
        "start of the week",
        "end of the week",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "morgens",
        "vormittag",
        "vormittags",
        "nachmittag",
        "nachmittags",
        "abends",
        "wochenanfang",
        "anfang der woche",
        "ende der woche",
        "montag",
        "dienstag",
        "mittwoch",
        "donnerstag",
        "freitag",
        "vor ort",
        "vor-ort",
        "persoenlich",
        "persönlich",
        "hybrid",
    )

    BOOKING_CONTEXT_TERMS = (
        "appointment options",
        "available appointments",
        "available slots",
        "appointment slots",
        "online-terminoptionen",
        "terminoptionen",
        "verfuegbare slots",
        "verfügbare slots",
        "verfuegbare termine",
        "verfügbare termine",
        "beratungsgespraech",
        "beratungsgespräch",
        "beratung",
    )

    BOOKING_CLARIFICATION_TERMS = (
        "do you prefer",
        "would you prefer",
        "which programme",
        "which program",
        "one short question",
        "final question",
        "when i know this",
        "bitte noch kurz",
        "eine kurze rueckfrage",
        "eine kurze rückfrage",
        "eine kurze letzte frage",
        "bevorzugen sie",
        "haben sie eine tagespraeferenz",
        "haben sie eine tagespräferenz",
        "sobald ich das weiss",
        "damit die slots besser passen",
    )

    RESPONSE_SHOWS_WIDGET_TERMS = (
        "i can show you",
        "contact details and available appointment slots are shown below",
        "appointment options are shown below",
        "available slots are shown below",
        "i can now show you",
        "ich kann ihnen nun",
        "ich kann ihnen jetzt",
        "unten werden ihnen",
        "unten finden sie",
        "unten sehen sie",
        "terminoptionen anzeigen",
        "verfuegbaren slots",
        "verfügbaren slots",
        "verfuegbaren termine",
        "verfügbaren termine",
    )

    RESPONSE_DEFER_TERMS = (
        "if you would like",
        "if you later wish",
        "you can ask me",
        "if that would be helpful",
        "sobald ich das weiss",
        "wenn ich das weiss",
        "damit die slots besser passen",
        "bitte noch kurz",
        "eine kurze rueckfrage",
        "eine kurze rückfrage",
        "eine kurze letzte frage",
        "bevorzugen sie",
        "have you got a preference",
        "do you prefer",
        "would you prefer",
        "which programme",
        "which program",
    )

    DIRECT_BOOKING_TERMS = (
        "book",
        "schedule",
        "appointment",
        "consultation",
        "need a consultation",
        "personal consultation",
        "speak with",
        "talk to an advisor",
        "talk to admissions",
        "connect me",
        "show me available",
        "show appointment",
        "available slots",
        "termin",
        "termin buchen",
        "termin vereinbaren",
        "beratungstermin",
        "beratungsgespraech",
        "beratungsgespräch",
        "ich brauche eine beratung",
        "ich moechte eine beratung",
        "ich möchte eine beratung",
        "ich will eine beratung",
        "beratung fuer",
        "beratung für",
        "persoenliche beratung",
        "persönliche beratung",
        "mit jemandem sprechen",
        "mit admissions sprechen",
        "mit der zulassung sprechen",
        "termine anzeigen",
        "verfuegbare termine",
        "verfügbare termine",
    )

    REJECTION_TERMS = (
        "do not want",
        "don't want",
        "no appointment",
        "not book",
        "not schedule",
        "no thanks",
        "no thank you",
        "kein termin",
        "keinen termin",
        "keine beratung",
        "nicht buchen",
        "nicht vereinbaren",
        "nein danke",
    )

    ACCEPTANCE_TERMS = (
        "yes",
        "yes please",
        "please do",
        "that would be helpful",
        "show me",
        "ja",
        "ja bitte",
        "gerne",
        "bitte",
        "mach das",
        "zeige",
    )

    @staticmethod
    def latest_response_offered_booking(latest_ai_message: str) -> bool:
        content_lower = latest_ai_message.lower()
        return any(term in content_lower for term in BookingIntentDetector.BOOKING_OFFER_TERMS)

    @staticmethod
    def is_booking_preference_follow_up(query: str) -> bool:
        query_lower = query.lower().strip()
        return bool(query_lower) and any(
            term in query_lower for term in BookingIntentDetector.BOOKING_PREFERENCE_TERMS
        )

    @staticmethod
    def latest_response_requested_booking_preferences(latest_ai_message: str) -> bool:
        content_lower = latest_ai_message.lower()
        return (
            any(term in content_lower for term in BookingIntentDetector.BOOKING_CONTEXT_TERMS)
            and any(term in content_lower for term in BookingIntentDetector.BOOKING_CLARIFICATION_TERMS)
        )

    @staticmethod
    def response_commits_to_showing_booking_widget(response: str) -> bool:
        response_lower = response.lower()
        return (
            any(term in response_lower for term in BookingIntentDetector.RESPONSE_SHOWS_WIDGET_TERMS)
            and not any(term in response_lower for term in BookingIntentDetector.RESPONSE_DEFER_TERMS)
        )

    @staticmethod
    def is_explicit_booking_intent(query: str, latest_ai_message: str = "") -> bool:
        query_lower = query.lower()

        def contains_term(term: str) -> bool:
            if term in {"yes", "ja", "bitte"}:
                return re.search(rf"\b{re.escape(term)}\b", query_lower) is not None
            return term in query_lower

        if any(contains_term(term) for term in BookingIntentDetector.REJECTION_TERMS):
            return False
        if any(contains_term(term) for term in BookingIntentDetector.DIRECT_BOOKING_TERMS):
            return True

        return (
            BookingIntentDetector.latest_response_offered_booking(latest_ai_message)
            and any(contains_term(term) for term in BookingIntentDetector.ACCEPTANCE_TERMS)
        )


class ProgrammeOverviewResponder:
    """Build legacy deterministic programme overview copy.

    This class is not a source of current programme facts. The corresponding
    answer path is disabled by DeterministicResponsePolicy.
    """

    @staticmethod
    def build_response(
        language: str,
        detailed: bool,
        detail_level: int,
        profile_context: bool = False,
        recommended_programme: str | None = None,
    ) -> str:
        if language == "en":
            return ProgrammeOverviewResponder._build_english_response(
                detailed=detailed,
                detail_level=detail_level,
                profile_context=profile_context,
                recommended_programme=recommended_programme,
            )
        return ProgrammeOverviewResponder._build_german_response(
            detailed=detailed,
            detail_level=detail_level,
            profile_context=profile_context,
            recommended_programme=recommended_programme,
        )

    @staticmethod
    def _build_english_response(
        detailed: bool,
        detail_level: int,
        profile_context: bool,
        recommended_programme: str | None,
    ) -> str:
        if not detailed:
            if not profile_context and not recommended_programme:
                return (
                    "At HSG, there are three relevant Executive MBA options. The main difference is not that one is "
                    "universally better, but their language, focus, network, and development goal.\n\n"
                    "1. **EMBA HSG**: German-speaking programme for DACH-focused general management, leadership, "
                    "strategy, finance, organisation, and governance.\n"
                    "2. **IEMBA HSG**: English-speaking international option for leaders who want global exposure, "
                    "international peer learning, and management perspective across markets.\n"
                    "3. **emba X**: English-speaking joint-degree option with **ETH Zurich** and **University of St.Gallen** "
                    "for leadership at the intersection of business, technology, innovation, and transformation.\n\n"
                    "Would you like details on costs, start dates, deadlines, duration, or admissions requirements, "
                    "or should I recommend the most suitable programme based on the information you share?"
                )

            if recommended_programme == "emba":
                return (
                    "Based on your German-language preference and leadership experience, **EMBA HSG** is the "
                    "strongest fit. Your professional and leadership experience is in the usual Executive MBA range; "
                    "formal eligibility still needs to be confirmed against the current admissions requirements.\n\n"
                    "**IEMBA HSG** remains relevant mainly if your next goal is international exposure. **emba X** "
                    "remains relevant mainly if your goal is technology, innovation, or transformation."
                )

            if recommended_programme == "iemba":
                return (
                    "Based on your international focus, **IEMBA HSG** is the strongest fit. It is the Executive MBA "
                    "option built around international management perspective, global peer learning, and cross-border "
                    "leadership.\n\n"
                    "**EMBA HSG** remains relevant mainly for German-speaking DACH general management. **emba X** "
                    "remains relevant mainly if technology, innovation, or transformation is the central goal."
                )

            if recommended_programme == "emba_x":
                return (
                    "Based on your technology, innovation, transformation, or sustainability focus, **emba X** is the "
                    "strongest fit. It is the Executive MBA option designed for leadership at the intersection of "
                    "business and technology with the ETH Zurich and University of St.Gallen joint-degree setting.\n\n"
                    "**IEMBA HSG** remains relevant mainly if international exposure is the primary goal. **EMBA HSG** "
                    "remains relevant mainly for German-speaking DACH general management."
                )

            return (
                "The information you shared helps clarify the admissions level; the Executive MBA options should be "
                "checked against the current requirements. The programme choice should now be based on your "
                "development goals, not on an automatic classification.\n\n"
                "1. **EMBA HSG**: strongest if your goal is DACH-focused general management, organisational leadership, "
                "strategy, finance, and governance.\n"
                "2. **IEMBA HSG**: strongest if your goal is international exposure, global peer learning, or cross-border work.\n"
                "3. **emba X**: strongest if your goal is digital transformation, technology, innovation, or large-scale change.\n\n"
                "Would you like details on costs, start dates, deadlines, duration, or admissions requirements, "
                "or should I recommend the most suitable programme based on the information you share?"
            )

        if detail_level <= 1:
            if not profile_context:
                return (
                    "More detail across all three programmes:\n\n"
                    "**EMBA HSG** aims to strengthen broad general-management judgement in the DACH context. It is "
                    "the most natural fit if the goal is stronger strategic, financial, organisational, governance, "
                    "negotiation, and leadership capability in German-speaking organisations.\n\n"
                    "**IEMBA HSG** aims to build international management perspective. The value is not only the "
                    "English language; it is the global cohort, international modules, and broader comparison across "
                    "markets, systems, and leadership environments.\n\n"
                    "**emba X** aims at leadership where business and technology meet. It is the strongest option if "
                    "the goal is digital transformation, innovation, technology-driven business models, AI/data "
                    "initiatives, or large organisational change. Its distinctive feature is the integrated **ETH "
                    "Zurich** plus **University of St.Gallen** joint-degree setting and access to both networks."
                )

            return (
                "More detail across all three programmes:\n\n"
                "**EMBA HSG** aims to strengthen broad general-management judgement for leaders in the DACH context. "
                "For a professional or leader comparing options, the practical value is strategy, finance, governance, "
                "organisation design, negotiation, and change leadership in German-speaking organisations. The capstone "
                "project can be tied to a real organisational or transformation topic.\n\n"
                "**IEMBA HSG** aims to build international management perspective. The value is not only the English "
                "language; it is the global cohort and modules across different regions. That is useful when your work "
                "involves international partners, cross-border teams, global markets, or comparison across business "
                "environments.\n\n"
                "**emba X** aims at leadership where business and technology meet. It is the most relevant option if "
                "your goals include digital transformation, technology-led business models, AI/data initiatives, "
                "innovation, or large organisational change. Its distinctive feature is the integrated **ETH Zurich** "
                "plus **University of St.Gallen** joint-degree setting and access to both alumni networks."
            )

        if not profile_context and not recommended_programme:
            return (
                "The next useful distinction is by goals and working context:\n\n"
                "- Choose **EMBA HSG** if the main goal is DACH-focused general management: strategy, finance, "
                "governance, organisation, negotiation, and leadership.\n"
                "- Choose **IEMBA HSG** if the main goal is international exposure: global peer learning, "
                "international modules, markets, organisations, and partnerships.\n"
                "- Choose **emba X** if the main goal is technology-led transformation: digitalisation, innovation, "
                "data/AI initiatives, new business models, or major change programmes.\n\n"
                "The next step is therefore not an automatic recommendation, but clarifying the development goal: "
                "DACH management depth, international management breadth, or technology-led transformation."
            )

        return (
            "The next useful distinction is by goals and working context:\n\n"
            "- Choose **EMBA HSG** if your main goal is stronger economic and organisational steering in the DACH "
            "environment: strategy, budgeting, governance, leadership, negotiation, and operational change.\n"
            "- Choose **IEMBA HSG** if your main goal is international exposure: learning with a global cohort, "
            "working across markets or organisations, and building confidence for international partnerships.\n"
            "- Choose **emba X** if your main goal is transformation through technology: digitalisation, innovation "
            "portfolios, data/AI initiatives, new business models, or culture change around new tools.\n\n"
            "Based on the information shared so far, all three can remain worth comparing. The deciding factor is "
            "whether your next development goal is DACH management depth, international management breadth, or "
            "technology-led transformation."
        )

    @staticmethod
    def _build_german_response(
        detailed: bool,
        detail_level: int,
        profile_context: bool,
        recommended_programme: str | None,
    ) -> str:
        if not detailed:
            if not profile_context and not recommended_programme:
                return (
                    "Bei HSG gibt es drei relevante Executive-MBA-Optionen. Der Unterschied liegt nicht darin, dass ein "
                    "Programm pauschal besser ist, sondern in Sprache, Fokus, Netzwerk und Entwicklungsziel.\n\n"
                    "1. **EMBA HSG**: deutschsprachig, DACH-Fokus, General Management, Leadership, Strategie, Finanzen, "
                    "Organisation und Governance.\n"
                    "2. **IEMBA HSG**: englischsprachig und international ausgerichtet, mit Fokus auf globale Perspektive, "
                    "internationale Peer Group und Führung über Märkte hinweg.\n"
                    "3. **emba X**: englischsprachiges Joint Degree mit **ETH Zürich** und **Universität St.Gallen**, mit "
                    "Fokus auf Business, Technologie, Innovation und Transformation.\n\n"
                    "Interessieren Sie sich für Kosten, Startdatum, Fristen, Dauer oder Zulassungsdetails, oder möchten "
                    "Sie, dass ich ein passendes Programm anhand Ihrer Angaben empfehle?"
                )

            if recommended_programme == "emba":
                return (
                    "Auf Basis Ihrer deutschsprachigen Präferenz und Ihrer Führungserfahrung ist **EMBA HSG** der "
                    "stärkste Fit. Ihre Berufs- und Führungserfahrung liegt im typischen Executive-MBA-Profil; die "
                    "formale Zulassung muss dennoch anhand der aktuellen Anforderungen geprüft werden.\n\n"
                    "**IEMBA HSG** bleibt vor allem relevant, wenn Internationalität Ihr nächstes Ziel ist. **emba X** "
                    "bleibt vor allem relevant, wenn Technologie, Innovation oder Transformation im Zentrum stehen."
                )

            if recommended_programme == "iemba":
                return (
                    "Auf Basis Ihres internationalen Fokus ist **IEMBA HSG** der stärkste Fit. Das Programm ist auf "
                    "internationale Managementperspektive, globale Peer Learning und Führung über Märkte hinweg "
                    "ausgerichtet.\n\n"
                    "**EMBA HSG** bleibt vor allem relevant für deutschsprachiges General Management im DACH-Kontext. "
                    "**emba X** bleibt vor allem relevant, wenn Technologie, Innovation oder Transformation im Zentrum stehen."
                )

            if recommended_programme == "emba_x":
                return (
                    "Auf Basis Ihres Fokus auf Technologie, Innovation, Transformation oder Nachhaltigkeit ist **emba X** "
                    "der stärkste Fit. Das Programm ist auf Führung an der Schnittstelle von Business und Technologie "
                    "ausgerichtet und verbindet **ETH Zürich** mit der **Universität St.Gallen**.\n\n"
                    "**IEMBA HSG** bleibt vor allem relevant, wenn Internationalität das Hauptziel ist. **EMBA HSG** "
                    "bleibt vor allem relevant für deutschsprachiges General Management im DACH-Kontext."
                )

            return (
                "Ihre Angaben helfen vor allem, die Zulassungsebene einzuordnen; die Executive-MBA-Optionen sollten anhand "
                "der aktuellen Anforderungen geprüft werden. Die Programmwahl sollte jetzt über Ihre Entwicklungsziele "
                "laufen, nicht über eine automatische Einordnung.\n\n"
                "1. **EMBA HSG**: naheliegend, wenn Sie DACH-orientiertes General Management, Strategie, Finanzen, Organisation und Governance vertiefen wollen.\n"
                "2. **IEMBA HSG**: naheliegend, wenn Sie internationaler arbeiten, vergleichen oder kooperieren möchten.\n"
                "3. **emba X**: naheliegend, wenn Digitalisierung, Technologie, Innovation oder grosse Transformation zentral sind.\n\n"
                "Interessieren Sie sich für Kosten, Startdatum, Fristen, Dauer oder Zulassungsdetails, oder möchten "
                "Sie, dass ich ein passendes Programm anhand Ihrer Angaben empfehle?"
            )

        if detail_level <= 1:
            if not profile_context:
                return (
                    "Weitere Details zu **allen drei Programmen**:\n\n"
                    "**EMBA HSG** zielt auf breite General-Management-Kompetenz im DACH-Raum. Das Programm ist sinnvoll, "
                    "wenn Sie Strategie, Finanzen, Governance, Organisation, Verhandlung und Change Management im "
                    "deutschsprachigen Kontext vertiefen möchten. Das Capstone-Projekt kann auf ein reales "
                    "Organisations- oder Transformationsvorhaben ausgerichtet werden.\n\n"
                    "**IEMBA HSG** zielt auf internationale Managementkompetenz. Der Mehrwert liegt in der englischsprachigen "
                    "globalen Kohorte, den internationalen Modulen und dem Vergleich verschiedener Märkte, Systeme und "
                    "Führungsumfelder.\n\n"
                    "**emba X** zielt auf Führung an der Schnittstelle von Business und Technologie. Das ist besonders "
                    "relevant, wenn Ihre Ziele Digitalisierung, datengetriebene Prozesse, Innovation, neue Geschäftsmodelle "
                    "oder grosse Transformationsprojekte betreffen. Der besondere Punkt ist die Kombination aus **ETH Zürich** "
                    "und **Universität St.Gallen** sowie der Zugang zu beiden Netzwerken."
                )

            return (
                "Weitere Details zu **allen drei Programmen**, ohne Sie vorschnell auf eines festzulegen:\n\n"
                "**EMBA HSG** zielt auf breite General-Management-Kompetenz im DACH-Raum. Das ist relevant, wenn Sie "
                "Strategie, Finanzen, Governance, Organisation, Verhandlung und Change Management stärken wollen. Das "
                "Capstone-Projekt kann direkt auf ein reales Organisations- oder Transformationsvorhaben ausgerichtet "
                "werden.\n\n"
                "**IEMBA HSG** zielt auf internationale Managementkompetenz. Der Mehrwert liegt in der englischsprachigen "
                "globalen Kohorte und den internationalen Modulen. Das ist besonders sinnvoll, wenn Sie mit internationalen "
                "Partnern, Märkten, Teams oder Organisationen arbeiten oder Führungsfragen über Ländergrenzen hinweg "
                "vergleichen möchten.\n\n"
                "**emba X** zielt auf Führung an der Schnittstelle von Business und Technologie. Das ist besonders relevant, "
                "wenn Ihre Ziele Digitalisierung, technologiegetriebene Geschäftsmodelle, datenbasierte Prozesse, "
                "Innovation oder grosse Transformationsprojekte betreffen. Der besondere Punkt ist die Kombination aus "
                "**ETH Zürich** und **Universität St.Gallen** sowie der Zugang zu beiden Netzwerken."
            )

        if not profile_context:
            return (
                "Die nächste sinnvolle Unterscheidung läuft über Ziele und Arbeitskontext:\n\n"
                "- **EMBA HSG** passt am besten, wenn der Schwerpunkt auf General Management im DACH-Raum liegt: "
                "Strategie, Finanzen, Governance, Organisation, Verhandlung und Leadership.\n"
                "- **IEMBA HSG** passt am besten, wenn Internationalität zentral ist: globale Peer Group, "
                "Auslandsmodule, internationale Märkte, Organisationen und Partnerschaften.\n"
                "- **emba X** passt am besten, wenn Technologie und Transformation im Zentrum stehen: Digitalisierung, "
                "Innovation, Daten-/AI-Projekte, neue Geschäftsmodelle oder grosse Veränderungsprogramme.\n\n"
                "Der nächste Schritt ist daher nicht eine pauschale Empfehlung, sondern die Klärung Ihres Ziels: "
                "DACH-Management, Internationalität oder technologiegetriebene Transformation."
            )

        return (
            "Die nächste sinnvolle Unterscheidung läuft über Ziele und Arbeitskontext:\n\n"
            "- **EMBA HSG** passt am besten, wenn Sie Ihre ökonomische, organisatorische und strategische Steuerung im "
            "DACH-Umfeld vertiefen wollen: Budget, Governance, Personalführung, Verhandlung und Change.\n"
            "- **IEMBA HSG** passt am besten, wenn Sie internationaler arbeiten möchten: Vergleich von Märkten und "
            "Organisationen, globale Peer Group, internationale Kooperationen oder länderübergreifende Verantwortung.\n"
            "- **emba X** passt am besten, wenn Technologie und Transformation im Zentrum stehen: Digitalisierung, "
            "datenbasierte Prozesse, neue Geschäftsmodelle, Innovationsportfolios oder kultureller Wandel.\n\n"
            "Anhand der bisherigen Angaben können alle drei Programme weiterhin vergleichbar bleiben. Ausschlaggebend "
            "ist, ob Ihr nächster Entwicklungsschwerpunkt DACH-Management, Internationalität oder technologiegetriebene "
            "Transformation ist."
        )


class LegacyProgrammeContentResponder:
    """Legacy deterministic programme-content text builders.

    These paths are disabled by policy; keeping the copy here prevents
    agent_chain.py from accumulating response constants.
    """

    @staticmethod
    def iemba_visa_response() -> str:
        return (
            "For the **IEMBA HSG**, US participants usually attend short, modular teaching blocks rather than "
            "relocating for a full-time degree. For short stays in Switzerland, US citizens can generally use "
            "**Schengen short-stay rules** of up to 90 days in any 180-day period, provided they meet normal entry "
            "conditions and do not take up local employment.\n\n"
            "If you plan to relocate to Switzerland or Europe, the question changes from a module visit to residence "
            "or work-permit planning. The binding answer comes from Swiss authorities; admissions can help you check "
            "the programme schedule against your travel pattern."
        )

    @staticmethod
    def iemba_apac_alumni_response() -> str:
        return (
            "For Asia-Pacific exposure, **IEMBA HSG** is the strongest HSG Executive MBA reference point. Its value is "
            "the combination of an English-speaking international cohort, Asia-facing learning components such as Japan "
            "or emerging-economy topics, and the broader University of St.Gallen alumni network.\n\n"
            "In practice, candidates usually look for connections in markets such as **Singapore, Hong Kong, Greater "
            "China, Japan, and Australia**. If APAC is central to your goals, admissions can help you speak with a "
            "recent alumnus or alumna from the region for a first-hand view."
        )

    @staticmethod
    def embax_comparison_response(language: str) -> str:
        if language == "de":
            return (
                "Der wichtigste Unterschied liegt im Fokus und in der Trägerschaft:\n\n"
                "- **EMBA HSG**: deutschsprachiges General-Management-Programm mit DACH-Fokus. Es eignet sich, wenn "
                "Sie Strategie, Finanzen, Organisation, Governance und Leadership im klassischen Managementkontext "
                "vertiefen möchten.\n"
                "- **emba X**: englischsprachiger Executive MBA von **ETH Zürich** und **Universität St.Gallen**. Er "
                "verbindet Management mit Technologie, Innovation, Transformation und Nachhaltigkeit.\n\n"
                "Kurz gesagt: **EMBA HSG** ist der stärkere klassische General-Management-Pfad; **emba X** ist der "
                "stärkere Pfad, wenn Technologie, digitale Transformation oder nachhaltige Innovation zentral sind."
            )
        return (
            "**EMBA HSG** is the German-speaking general-management route with a DACH focus. **emba X** is the "
            "English-speaking joint programme from ETH Zurich and the University of St.Gallen, focused on business, "
            "technology, innovation, transformation, and sustainability."
        )

    @staticmethod
    def embax_language_response(language: str) -> str:
        if language == "de":
            return (
                "**emba X** wird vollständig **auf Englisch** unterrichtet. Das gilt für Module, Unterlagen, "
                "Gruppenarbeiten, Leistungsnachweise und die Arbeit im internationalen Teilnehmendenfeld.\n\n"
                "Wenn Sie ein deutschsprachiges berufsbegleitendes Executive-MBA-Programm suchen, ist der **EMBA HSG** "
                "die naheliegendere Alternative."
            )
        return (
            "**emba X** is taught entirely in **English**, including modules, materials, group work, assessments, "
            "and programme communication."
        )

    @staticmethod
    def too_early_for_executive_mba_response(language: str) -> str:
        if language == "de":
            return (
                "Das ist ein verständlicher nächster Schritt in Ihrer Planung, aber mit Bachelorabschluss und nur "
                "**2 Jahren Berufserfahrung** ist ein **Executive MBA** wahrscheinlich noch zu früh. Die "
                "HSG Executive-MBA-Programme richten sich in der Regel an Personen mit mindestens etwa **5 Jahren "
                "Berufserfahrung** bzw. rund **3 Jahren Führungserfahrung**; dieses Profil erfüllen Sie aktuell "
                "voraussichtlich noch nicht.\n\n"
                "Als HSG-Alternative ist der reguläre **MBA** naheliegender: https://www.mba.unisg.ch/. Für passende "
                "Alternativen kann Ihnen ein **Kontakt zu Admissions** helfen, Ihr Profil zu prüfen und den richtigen "
                "nächsten Schritt einzuordnen. E-Mail: emba@unisg.ch."
            )
        return (
            "That is a reasonable next planning step, but with a bachelor's degree and only **2 years of work "
            "experience**, an **Executive MBA** is likely too early. The HSG Executive MBA programmes are usually "
            "aimed at candidates with at least about **5 years of professional experience** or around **3 years "
            "of leadership experience**; your current profile is therefore probably not yet at Executive MBA level.\n\n"
            "The regular **MBA** is the more likely HSG alternative: https://www.mba.unisg.ch/. A **contact with "
            "admissions** can help review your profile and point you to the right alternative. Email: emba@unisg.ch."
        )
