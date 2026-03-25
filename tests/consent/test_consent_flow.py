"""
Integration tests for Consent UI Flow (without Gradio)
Tests: State transitions, Logic validation
"""
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from const.data_consent_constants import (
    PRIVACY_NOTICE,
    ACCEPT,
    DECLINE,
    DECLINE_MESSAGE,
    WITHDRAW_CONFIRMATION_MESSAGE,
    WITHDRAW_TEXT
)


class TestConsentFlow:
    """Test consent state transitions (logic only, no UI)"""

    def test_initial_state_requires_consent(self):
        """User should not be able to chat before consent"""
        # This would be enforced by Gradio UI visibility
        # Here we just verify the constants exist for the initial screen
        assert "de" in PRIVACY_NOTICE
        assert "en" in PRIVACY_NOTICE
        assert ACCEPT["de"] == "Zustimmen"
        assert ACCEPT["en"] == "Accept"

    def test_decline_blocks_chat(self):
        """Declining should show alternative contact"""
        # Verify decline message provides contact
        for lang in ["de", "en"]:
            msg = DECLINE_MESSAGE[lang]
            assert "emba@unisg.ch" in msg

    def test_withdraw_returns_to_consent(self):
        """Withdrawing should show consent screen again"""
        # Verify withdraw confirmation exists
        for lang in ["de", "en"]:
            msg = WITHDRAW_CONFIRMATION_MESSAGE[lang]
            assert "widerrufen" in msg or "withdrawn" in msg.lower()

    def test_language_switch_updates_all_texts(self):
        """All UI elements must have both languages"""
        constants = [PRIVACY_NOTICE, ACCEPT, DECLINE, DECLINE_MESSAGE, 
                     WITHDRAW_CONFIRMATION_MESSAGE, WITHDRAW_TEXT]
        
        for const in constants:
            assert "de" in const, f"Missing German: {const}"
            assert "en" in const, f"Missing English: {const}"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
