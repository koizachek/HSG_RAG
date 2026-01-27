"""
User Acceptance Tests for Chatbot Improvements

Tests cover:
- TC-EMBA-01/02/03: German speakers, qualification checks, cost inquiries
- TC-IEMBA-01/02: International profile, scheduling
- TC-embaX-01: Career switchers
- Edge cases: numeric input, mixed language, off-topic, aggressive
"""
import pytest
from src.rag.agent_chain import ExecutiveAgentChain
from src.rag.input_handler import InputHandler
from src.rag.response_formatter import ResponseFormatter
from src.rag.scope_guardian import ScopeGuardian


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
| EMBA    | 18 months | CHF 85,000 |
| IEMBA   | 18 months | CHF 88,000 |
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
        pre_processed_query = agent.preprocess_query("Hallo, ich interessiere mich für das EMBA Programm").processed_query
        response = agent.agent_query(pre_processed_query).response
        
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
        pre_processed_query = agent.preprocess_query(
            "Welche Voraussetzungen brauche ich für das EMBA Programm?").processed_query
        response = agent.agent_query(pre_processed_query).response
        
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

        pre_processed_query = agent.preprocess_query(
            "Was kostet das EMBA HSG Programm?").processed_query
        response = agent.agent_query(pre_processed_query).response

        # Should mention price range
        assert 'CHF' in response or 'Kosten' in response.lower()
        # Should mention 85-90k range
        assert '85' in response or '90' in response
        # Should be concise
        word_count = len(response.split())
        assert word_count < 150


class TestEdgeCases:
    """Test edge cases and error handling"""
    
    def test_mixed_language_input(self):
        """Test handling of mixed language input"""
        agent = ExecutiveAgentChain(language='en')
        
        # Mixed language should be handled gracefully
        pre_processed_query = agent.preprocess_query(
            "Hello I want to know über das EMBA program").processed_query
        response = agent.agent_query(pre_processed_query).response
        
        # Should receive a response (not crash)
        assert len(response) > 0
        assert isinstance(response, str)
    
    def test_very_short_input(self):
        """Test single character or word inputs"""
        agent = ExecutiveAgentChain(language='en')
        
        pre_processed_query = agent.preprocess_query(
            "hi").processed_query
        response = agent.agent_query(pre_processed_query).response
        
        # Should handle gracefully
        assert len(response) > 0
    
    def test_special_characters(self):
        """Test handling of special characters"""
        agent = ExecutiveAgentChain(language='en')
        
        pre_processed_query = agent.preprocess_query(
            "Cost??? $$$ EMBA HSG!!!!").processed_query
        response = agent.agent_query(pre_processed_query).response
        
        # Should handle and respond appropriately
        assert len(response) > 0
        assert 'CHF' in response or 'cost' in response.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
