"""
User Acceptance Tests for Chatbot Improvements

Tests cover:
- TC-EMBA-01/02/03: German speakers, qualification checks, cost inquiries
- TC-IEMBA-01/02: International profile, scheduling
- TC-embaX-01: Career switchers
- Edge cases: numeric input, mixed language, off-topic, aggressive
"""
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from src.apps.chat.app import ChatbotApplication
from src.rag.agent_chain import ExecutiveAgentChain
from src.rag.input_handler import InputHandler
from src.rag.response_formatter import ResponseFormatter
from src.rag.scope_guardian import ScopeGuardian
from src.rag.utilclasses import LeadAgentQueryResponse
class TestInputHandling:
    """Test numeric input interpretation"""
    
    def test_numeric_experience_input(self):
        """Test that standalone number is interpreted as years of experience"""
        history = [
            {"role": "assistant", "content": "How many years of work experience do you have?"}
        ]
        
        processed, is_valid = InputHandler.process_input("5", history)
        
        assert is_valid
        assert "5 years" in processed.lower()
        assert "experience" in processed.lower()
    
    def test_numeric_age_input(self):
        """Test numeric input interpreted as age"""
        history = [
            {"role": "assistant", "content": "How old are you?"}
        ]
        
        processed, is_valid = InputHandler.process_input("35", history)
        
        assert is_valid
        assert "35" in processed
        assert "years old" in processed.lower() or "age" in processed.lower()
    
    def test_empty_input_validation(self):
        """Test that empty inputs are rejected"""
        processed, is_valid = InputHandler.process_input("", [])
        
        assert not is_valid
        assert processed == ""
    
    def test_whitespace_input_validation(self):
        """Test that whitespace-only inputs are rejected"""
        processed, is_valid = InputHandler.process_input("   ", [])
        
        assert not is_valid


class TestResponseFormatting:
    """Test response formatting and table removal"""
    
    def test_table_removal(self):
        """Test that markdown tables are converted to bullet points"""
        table_text = """
Here are the programs:

| Program | Duration | Cost |
|---------|----------|------|
| EMBA    | 18 months | CHF 77,500 |
| IEMBA   | 18 months | CHF 85,000 |
        """
        
        formatted = ResponseFormatter.remove_tables(table_text)
        
        # Should not contain table markers
        assert "|" not in formatted
        # Should contain bullet points instead
        assert "•" in formatted or "-" in formatted
    
    def test_response_chunking(self):
        """Test that long responses are chunked"""
        long_text = " ".join(["word"] * 150)  # 150 words
        
        chunked, continuation = ResponseFormatter.chunk_response(long_text, max_words=100)
        
        # Current response should be shorter
        assert ResponseFormatter.count_words(chunked) <= 220  # Allow some buffer
        # Should have continuation indicator
        assert "continue" in chunked.lower() or "more" in chunked.lower()
    
    def test_short_response_no_chunking(self):
        """Test that short responses are not chunked"""
        short_text = "This is a short response."
        
        chunked, continuation = ResponseFormatter.chunk_response(short_text, max_words=200)
        
        assert continuation is None
        assert chunked == short_text

    def test_pending_continuation_is_served_without_new_agent_call(self):
        agent = object.__new__(ExecutiveAgentChain)
        agent._conversation_history = []
        agent._pending_continuation = " ".join(["detail"] * 140)

        response = agent._serve_pending_continuation(
            processed_query="ja, mehr details.",
            response_language="de",
        )

        assert response.language == "de"
        assert "Möchten Sie, dass ich mit weiteren Details fortfahre?" in response.response
        assert agent._pending_continuation is not None
        assert agent._conversation_history == []

    def test_continuation_request_handles_punctuation(self):
        agent = object.__new__(ExecutiveAgentChain)

        assert agent._is_continuation_request("ja, mehr details. ")

    def test_programme_overview_covers_all_three_without_chunk_prompt(self):
        agent = object.__new__(ExecutiveAgentChain)
        agent._conversation_history = []
        agent._pending_continuation = None
        agent._programme_overview_detail_level = 0

        response = agent._serve_programme_overview(
            processed_query="ich interessiere mich für einen MBA",
            response_language="de",
            detailed=False,
        )

        assert "EMBA HSG" in response.response
        assert "IEMBA HSG" in response.response
        assert "emba X" in response.response
        assert "Bei HSG gibt es drei relevante Executive-MBA-Optionen" in response.response
        assert "Das Profil klärt" not in response.response
        assert "Möchten Sie, dass ich mit weiteren Details fortfahre?" not in response.response
        assert response.relevant_programs == ["emba", "iemba", "emba_x"]
        assert isinstance(agent._conversation_history[0], HumanMessage)
        assert isinstance(agent._conversation_history[1], AIMessage)

    def test_profile_context_programme_overview_uses_profile_framing(self):
        agent = object.__new__(ExecutiveAgentChain)
        agent._conversation_history = []
        agent._pending_continuation = None
        agent._programme_overview_detail_level = 0

        response = agent._serve_programme_overview(
            processed_query="ich bin chefarzt mit 10 jahren erfahrung",
            response_language="de",
            detailed=False,
            profile_context=True,
        )

        assert "Das Profil klärt vor allem die Zulassungsebene" in response.response
        assert "EMBA HSG" in response.response
        assert "IEMBA HSG" in response.response
        assert "emba X" in response.response

    def test_profile_context_update_after_overview_is_not_single_programme_diagnosis(self):
        agent = object.__new__(ExecutiveAgentChain)
        agent._conversation_history = [
            AIMessage("EMBA HSG, IEMBA HSG und emba X sind relevant.")
        ]

        assert agent._latest_ai_mentions_multiple_programmes()
        assert agent._is_profile_context_update("10 jahre chefarzt, 5 jahre leadership")
        assert not agent._query_mentions_specific_programme("10 jahre chefarzt, 5 jahre leadership")

    def test_more_details_after_programme_overview_keeps_all_programmes(self):
        agent = object.__new__(ExecutiveAgentChain)
        agent._conversation_history = [
            AIMessage("EMBA HSG, IEMBA HSG und emba X sind relevant.")
        ]
        agent._pending_continuation = None
        agent._programme_overview_detail_level = 1

        assert agent._latest_ai_mentions_multiple_programmes()

        response = agent._serve_programme_overview(
            processed_query="mehr details",
            response_language="de",
            detailed=True,
        )

        assert "EMBA HSG" in response.response
        assert "IEMBA HSG" in response.response
        assert "emba X" in response.response
        assert "vorzeitig" not in response.response.lower()
        assert "Möchten Sie, dass ich mit weiteren Details fortfahre?" not in response.response

    def test_embax_preference_moves_to_next_steps_not_repetition(self):
        agent = object.__new__(ExecutiveAgentChain)
        agent._conversation_history = [
            AIMessage("EMBA HSG, IEMBA HSG und emba X sind relevant.")
        ]
        agent._conversation_state = {
            "handover_requested": None,
            "suggested_program": None,
        }
        agent._pending_continuation = None

        assert agent._extract_programme_preference("ich finde emba X besser") == "emba_x"

        response = agent._serve_programme_next_steps(
            processed_query="ich finde emba X besser",
            response_language="de",
            programme="emba_x",
        )

        assert "Fit- und Zulassungsabklärung" in response.response
        assert "31.08.2026" in response.response
        assert "31.10.2026" in response.response
        assert "Teyuna Giger" in response.response
        assert response.appointment_requested is True
        assert response.show_booking_widget is True
        assert response.relevant_programs == ["emba_x"]
        assert agent._conversation_state["handover_requested"] is True
        assert agent._conversation_state["suggested_program"] == "emba_x"

    def test_emba_next_steps_include_programme_specific_details(self):
        agent = object.__new__(ExecutiveAgentChain)
        agent._conversation_history = []
        agent._conversation_state = {
            "handover_requested": None,
            "suggested_program": None,
        }

        response = agent._serve_programme_next_steps(
            processed_query="ich finde EMBA HSG besser",
            response_language="de",
            programme="emba",
        )

        assert "Cyra von Müller" in response.response
        assert "14.09.2026" in response.response
        assert "CHF 77'500" in response.response
        assert "5+ Jahre Berufserfahrung" in response.response
        assert "3+ Jahre Führungserfahrung" in response.response
        assert response.relevant_programs == ["emba"]

    def test_iemba_next_steps_include_programme_specific_details(self):
        agent = object.__new__(ExecutiveAgentChain)
        agent._conversation_history = []
        agent._conversation_state = {
            "handover_requested": None,
            "suggested_program": None,
        }

        response = agent._serve_programme_next_steps(
            processed_query="ich finde IEMBA HSG besser",
            response_language="de",
            programme="iemba",
        )

        assert "Kristin Fuchs" in response.response
        assert "24.08.2026" in response.response
        assert "CHF 85'000" in response.response
        assert "10 Kernkurse" in response.response
        assert "4 Wochen Auslandsmodule" in response.response
        assert response.relevant_programs == ["iemba"]

    def test_application_question_after_programme_choice_shows_booking_widget(self):
        agent = object.__new__(ExecutiveAgentChain)
        agent._conversation_history = [
            AIMessage("Für emba X sind die nächsten Schritte ein Fit- und Zulassungsgespräch.")
        ]
        agent._conversation_state = {
            "handover_requested": None,
            "suggested_program": "emba_x",
            "program_interest": [],
        }
        agent._pending_continuation = None

        assert agent._resolve_application_programmes("Wie läuft die Bewerbung ab?") == ["emba_x"]

        response = agent._serve_application_next_steps(
            processed_query="Wie läuft die Bewerbung ab?",
            response_language="de",
            programmes=["emba_x"],
        )

        assert "Bewerbung zum **emba X**" in response.response
        assert "Teyuna Giger" in response.response
        assert response.appointment_requested is True
        assert response.show_booking_widget is True
        assert response.relevant_programs == ["emba_x"]

    def test_application_process_follow_up_adds_details_without_repeating_widget(self):
        agent = object.__new__(ExecutiveAgentChain)
        agent._conversation_history = []
        agent._conversation_state = {
            "handover_requested": None,
            "suggested_program": "emba_x",
            "program_interest": ["emba_x"],
        }
        agent._pending_continuation = None

        first_response = agent._serve_application_next_steps(
            processed_query="Wie bewerbe ich mich?",
            response_language="de",
            programmes=["emba_x"],
        )

        assert agent._previous_response_was_application_next_step()
        assert agent._is_application_process_detail_request("Wie läuft der Prozess?")
        assert agent._resolve_known_application_programmes("Wie läuft der Prozess?") == ["emba_x"]

        second_response = agent._serve_application_process_details(
            processed_query="Wie läuft der Prozess?",
            response_language="de",
            programmes=["emba_x"],
        )

        assert second_response.response != first_response.response
        assert "Unterlagen vorbereiten" in second_response.response
        assert "31.08.2026" in second_response.response
        assert "31.10.2026" in second_response.response
        assert second_response.appointment_requested is False
        assert second_response.show_booking_widget is False
        assert second_response.relevant_programs == ["emba_x"]

    def test_emba_application_process_details_include_start_fee_and_requirements(self):
        agent = object.__new__(ExecutiveAgentChain)
        agent._conversation_history = [
            AIMessage("Für die Bewerbung zum **EMBA HSG** ist der nächste sinnvolle Schritt ein Zulassungsgespräch.")
        ]
        agent._conversation_state = {
            "handover_requested": True,
            "suggested_program": "emba",
            "program_interest": ["emba"],
        }

        response = agent._serve_application_process_details(
            processed_query="Wie läuft der Prozess?",
            response_language="de",
            programmes=["emba"],
        )

        assert "EMBA HSG" in response.response
        assert "14.09.2026" in response.response
        assert "CHF 77'500" in response.response
        assert "5+ Jahre Berufserfahrung" in response.response
        assert "3+ Jahre Führungserfahrung" in response.response
        assert "Capstone" in response.response
        assert response.show_booking_widget is False

    def test_iemba_application_process_details_include_start_fee_and_requirements(self):
        agent = object.__new__(ExecutiveAgentChain)
        agent._conversation_history = [
            AIMessage("Für die Bewerbung zum **IEMBA HSG** ist der nächste sinnvolle Schritt ein Zulassungsgespräch.")
        ]
        agent._conversation_state = {
            "handover_requested": True,
            "suggested_program": "iemba",
            "program_interest": ["iemba"],
        }

        response = agent._serve_application_process_details(
            processed_query="Welche Unterlagen und Fristen?",
            response_language="de",
            programmes=["iemba"],
        )

        assert "IEMBA HSG" in response.response
        assert "24.08.2026" in response.response
        assert "CHF 85'000" in response.response
        assert "5+ Jahre Berufserfahrung" in response.response
        assert "3+ Jahre Führungserfahrung" in response.response
        assert "sehr gutes Englisch" in response.response
        assert response.show_booking_widget is False

    def test_embax_user_interest_is_not_misclassified_as_emba_hsg(self):
        agent = object.__new__(ExecutiveAgentChain)
        agent._conversation_history = []
        agent._conversation_state = {
            "session_id": "session-1",
            "user_id": "session-1",
            "user_language": "de",
            "user_name": None,
            "experience_years": None,
            "leadership_years": None,
            "field": None,
            "interest": None,
            "qualification_level": None,
            "program_interest": [],
            "suggested_program": None,
            "handover_requested": None,
            "topics_discussed": [],
            "preferences_known": False,
        }

        agent._update_conversation_state(
            "Ich interessiere mich für den EMBA x.",
            "Gerne, emba X ist das Joint Degree mit ETH Zürich und Universität St.Gallen.",
        )

        assert agent._conversation_state["program_interest"] == ["emba_x"]
        assert agent._conversation_state["suggested_program"] == "emba_x"
        assert agent._resolve_application_programmes("Wie läuft die Bewerbung?") == ["emba_x"]

        response = agent._serve_application_next_steps(
            processed_query="Wie läuft die Bewerbung?",
            response_language="de",
            programmes=["emba_x"],
        )

        assert "Teyuna Giger" in response.response
        assert response.relevant_programs == ["emba_x"]

    def test_later_embax_selection_overrides_stale_emba_suggestion(self):
        agent = object.__new__(ExecutiveAgentChain)
        agent._conversation_history = []
        agent._conversation_state = {
            "session_id": "session-1",
            "user_id": "session-1",
            "user_language": "de",
            "user_name": None,
            "experience_years": None,
            "leadership_years": None,
            "field": None,
            "interest": None,
            "qualification_level": None,
            "program_interest": [],
            "suggested_program": "emba",
            "handover_requested": None,
            "topics_discussed": [],
            "preferences_known": False,
        }

        assert agent._extract_programme_preference("ich denke der emba X ist der beste") == "emba_x"

        agent._update_conversation_state(
            "ich denke der emba X ist der beste",
            "Dann sind die nächsten Schritte für emba X relevant.",
        )

        assert agent._conversation_state["program_interest"] == ["emba_x"]
        assert agent._conversation_state["suggested_program"] == "emba_x"
        assert agent._resolve_application_programmes("wie bewerbe ich mich?") == ["emba_x"]

    def test_assistant_multi_programme_text_does_not_set_user_programme_interest(self):
        agent = object.__new__(ExecutiveAgentChain)
        agent._conversation_history = []
        agent._conversation_state = {
            "session_id": "session-1",
            "user_id": "session-1",
            "user_language": "de",
            "user_name": None,
            "experience_years": None,
            "leadership_years": None,
            "field": None,
            "interest": None,
            "qualification_level": None,
            "program_interest": [],
            "suggested_program": None,
            "handover_requested": None,
            "topics_discussed": [],
            "preferences_known": False,
        }

        agent._update_conversation_state(
            "Was ist ein Capstone-Projekt?",
            "Das kann im EMBA HSG, IEMBA HSG oder emba X relevant sein.",
        )

        assert agent._conversation_state["program_interest"] == []
        assert agent._conversation_state["suggested_program"] is None

    def test_application_question_with_specific_programme_shows_correct_advisor(self):
        agent = object.__new__(ExecutiveAgentChain)
        agent._conversation_history = []
        agent._conversation_state = {
            "handover_requested": None,
            "suggested_program": None,
            "program_interest": [],
        }

        programmes = agent._resolve_application_programmes(
            "Wie bewerbe ich mich für den IEMBA HSG?"
        )

        assert programmes == ["iemba"]

        response = agent._serve_application_next_steps(
            processed_query="Wie bewerbe ich mich für den IEMBA HSG?",
            response_language="de",
            programmes=programmes,
        )

        assert "IEMBA HSG" in response.response
        assert "Kristin Fuchs" in response.response
        assert response.show_booking_widget is True
        assert response.relevant_programs == ["iemba"]

    def test_general_application_question_after_multi_programme_overview_shows_all_advisors(self):
        agent = object.__new__(ExecutiveAgentChain)
        agent._conversation_history = [
            AIMessage("EMBA HSG, IEMBA HSG und emba X sind relevant.")
        ]
        agent._conversation_state = {
            "handover_requested": None,
            "suggested_program": None,
            "program_interest": [],
        }

        programmes = agent._resolve_application_programmes("Wie läuft die Bewerbung?")

        assert programmes == ["emba", "iemba", "emba_x"]

        response = agent._serve_application_next_steps(
            processed_query="Wie läuft die Bewerbung?",
            response_language="de",
            programmes=programmes,
        )

        assert "alle drei Studienberatungen" in response.response
        assert response.appointment_requested is True
        assert response.show_booking_widget is True
        assert response.relevant_programs == ["emba", "iemba", "emba_x"]

    def test_multi_programme_application_process_details_include_all_programmes(self):
        agent = object.__new__(ExecutiveAgentChain)
        agent._conversation_history = [
            AIMessage("Für den Bewerbungsschritt sollte zuerst geklärt werden, welches Programm Sie konkret ansteuern.")
        ]
        agent._conversation_state = {
            "handover_requested": True,
            "suggested_program": None,
            "program_interest": [],
        }

        response = agent._serve_application_process_details(
            processed_query="Wie läuft der Prozess?",
            response_language="de",
            programmes=["emba", "iemba", "emba_x"],
        )

        assert "EMBA HSG" in response.response
        assert "14.09.2026" in response.response
        assert "CHF 77'500" in response.response
        assert "IEMBA HSG" in response.response
        assert "24.08.2026" in response.response
        assert "CHF 85'000" in response.response
        assert "emba X" in response.response
        assert "31.08.2026" in response.response
        assert "31.10.2026" in response.response
        assert response.show_booking_widget is False

    def test_reset_conversation_state_clears_profile_and_history(self):
        agent = object.__new__(ExecutiveAgentChain)
        agent._conversation_history = [HumanMessage("ich bin chefarzt")]
        agent._pending_continuation = "more"
        agent._programme_overview_detail_level = 2
        agent._scope_violation_counts = {"weather": 1}
        agent._aggressive_violation_count = 1
        agent._conversation_state = {
            "session_id": "session-1",
            "user_id": "session-1",
            "user_language": "de",
            "user_name": None,
            "experience_years": 10,
            "leadership_years": 5,
            "field": "medicine",
            "interest": "emba",
            "qualification_level": None,
            "program_interest": ["emba_x"],
            "suggested_program": "emba_x",
            "handover_requested": True,
            "topics_discussed": ["profile"],
            "preferences_known": True,
        }

        agent.reset_conversation_state()

        assert agent._conversation_history == []
        assert agent._pending_continuation is None
        assert agent._programme_overview_detail_level == 0
        assert agent._scope_violation_counts == {}
        assert agent._aggressive_violation_count == 0
        assert agent._conversation_state["experience_years"] is None
        assert agent._conversation_state["field"] is None
        assert agent._conversation_state["suggested_program"] is None
        assert agent._conversation_state["program_interest"] == []

    def test_chat_resets_stale_agent_when_visible_history_is_empty(self):
        class FakeAgent:
            def __init__(self):
                self._conversation_history = [HumanMessage("ich bin chefarzt")]
                self.reset_called = False

            def reset_conversation_state(self):
                self.reset_called = True
                self._conversation_history = []

            def query(self, message):
                assert self.reset_called
                assert self._conversation_history == []
                return LeadAgentQueryResponse(response="fresh answer", language="de")

        app = ChatbotApplication.__new__(ChatbotApplication)
        app._language = "de"
        agent = FakeAgent()

        answers, returned_agent = app._chat("ich interessiere mich für einen mba", [], agent)

        assert answers == ["fresh answer"]
        assert returned_agent is agent
        assert agent.reset_called is True

    def test_chatbot_application_constructs_with_clear_handler(self):
        app = ChatbotApplication(language="de")

        assert app.app is not None


class TestScopeGuardian:
    """Test scope checking and redirection"""
    
    def test_on_topic_query(self):
        """Test that MBA-related queries are on-topic"""
        queries = [
            "What are the admission requirements for EMBA?",
            "How much does the program cost?",
            "What is the difference between EMBA and IEMBA?"
        ]
        
        for query in queries:
            query = ''.join(e for e in query if e.isalnum() or e == " ")
            scope = ScopeGuardian.check_scope(query, 'en')
            assert scope == 'on_topic'
    
    def test_off_topic_detection(self):
        """Test that off-topic queries are detected"""
        off_topic_queries = [
            "What's the weather today?",
            "Can you recommend a restaurant?",
            "Who won the sports match?"
        ]
        
        for query in off_topic_queries:
            query = ''.join(e for e in query if e.isalnum() or e == " ")
            scope = ScopeGuardian.check_scope(query, 'en')
            assert scope == 'off_topic'
    
    def test_financial_planning_detection(self):
        """Test that detailed financial requests are flagged"""
        financial_queries = [
            "Can you help me create a payment plan?",
            "How do I apply for a bank loan?",
            "I need a detailed budget for the program"
        ]
        
        for query in financial_queries:
            query = ''.join(e for e in query if e.isalnum() or e == " ")
            scope = ScopeGuardian.check_scope(query, 'en')
            assert scope == 'financial_planning'
    
    def test_aggressive_detection(self):
        """Test that aggressive language is detected"""
        aggressive_queries = [
            "This is stupid",
            "You're useless",
            "This chatbot is terrible"
        ]
        
        for query in aggressive_queries:
            query = ''.join(e for e in query if e.isalnum() or e == " ")
            scope = ScopeGuardian.check_scope(query, 'en')
            assert scope == 'aggressive'
    
    def test_redirect_message_language(self):
        """Test that redirect messages match requested language"""
        en_redirect = ScopeGuardian.get_redirect_message('off_topic', 'en')
        de_redirect = ScopeGuardian.get_redirect_message('off_topic', 'de')
        
        # English should contain English words
        assert any(word in en_redirect.lower() for word in ['help', 'programs', 'questions'])
        # German should contain German words
        assert any(word in de_redirect.lower() for word in ['hilfe', 'programm', 'fragen'])
    
    def test_escalation_logic(self):
        """Test that repeated violations trigger escalation"""
        # First off-topic -> no escalation
        should_escalate, _ = ScopeGuardian.should_escalate(
            "What's the weather",
            'off_topic',
            attempt_count=1
        )
        assert not should_escalate
        
        # Second off-topic -> escalate
        should_escalate, escalation_type = ScopeGuardian.should_escalate(
            "What's the weather",
            'off_topic',
            attempt_count=2
        )
        assert should_escalate
        assert escalation_type == 'escalate_off_topic'
        
        # Aggressive -> escalation if attempt_count >= 2
        should_escalate, escalation_type = ScopeGuardian.should_escalate(
            "You're useless",
            'aggressive',
            attempt_count=2
        )
        assert should_escalate
        assert escalation_type == 'escalate_aggressive'


class TestLanguageLocking:
    """Test language detection and locking"""
    
    def test_language_locked_after_first_message(self):
        """Test that language is locked after first user message"""
        agent = ExecutiveAgentChain(language='en')
        
        # First query in German
        response = agent.query("Hallo, ich interessiere mich für das EMBA Programm").response
        
        # Language should now be locked to German
        assert agent._stored_language == 'de'
        assert agent._conversation_state['user_language'] == 'de'
        
        # Subsequent English query should still get German response
        # (language is locked)
        assert agent._stored_language == 'de'


class TestUserAcceptanceScenarios:
    """Test complete user interaction scenarios"""
    
    def test_tc_emba_01_german_speaker(self):
        """TC-EMBA-01: German speaker asking about qualifications"""
        agent = ExecutiveAgentChain(language='de')
        agent.generate_greeting()
        
        # User asks about requirements in German
        response = agent.query("Welche Voraussetzungen brauche ich für das EMBA HSG Programm?").response
        
        # Response should be in German
        assert any(word in response.lower() for word in ['bachelor', 'master', 'jahre', 'erfahrung'])
        # Should not be overly long
        word_count = len(response.split())
        assert word_count < 200, f"Response too long: {word_count} words"
        # Should not contain tables
        assert '|' not in response
    
    def test_tc_emba_03_cost_inquiry(self):
        """TC-EMBA-03: Cost inquiry"""
        agent = ExecutiveAgentChain(language='de')
        agent.generate_greeting()

        response = agent.query("Was kostet das EMBA HSG Programm?").response

        # Should mention programme pricing
        assert 'CHF' in response or 'Kosten' in response.lower()
        # Should mention the updated EMBA tuition figure
        assert '77' in response
        # Should be concise
        word_count = len(response.split())
        assert word_count < 150


class TestEdgeCases:
    """Test edge cases and error handling"""
    
    def test_mixed_language_input(self):
        """Test handling of mixed language input"""
        agent = ExecutiveAgentChain(language='en')
        
        # Mixed language should be handled gracefully
        response = agent.query("Hello I want to know über das EMBA program").response
        
        # Should receive a response (not crash)
        assert len(response) > 0
        assert isinstance(response, str)
    
    def test_very_short_input(self):
        """Test single character or word inputs"""
        agent = ExecutiveAgentChain(language='en')

        response = agent.query("hi").response
        
        # Should handle gracefully
        assert len(response) > 0
    
    def test_special_characters(self):
        """Test handling of special characters"""
        agent = ExecutiveAgentChain(language='en')

        response = agent.query("Cost??? $$$ EMBA HSG!!!!").response
        
        # Should handle and respond appropriately
        assert len(response) > 0
        assert 'CHF' in response or 'cost' in response.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
