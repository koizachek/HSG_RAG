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
    BOOK_TEXT,
    BOOKING_WIDGET_HTML,
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

    def test_withdrawal_is_explained_in_privacy_notice_not_as_chat_action(self):
        """Withdrawal remains a privacy right, not the post-consent booking action"""
        assert "widerrufen" in PRIVACY_NOTICE["de"]
        assert "withdraw" in PRIVACY_NOTICE["en"].lower()

    def test_language_switch_updates_all_texts(self):
        """All UI elements must have both languages"""
        constants = [PRIVACY_NOTICE, ACCEPT, DECLINE, DECLINE_MESSAGE, 
                     BOOK_TEXT, BOOKING_WIDGET_HTML]
        
        for const in constants:
            assert "de" in const, f"Missing German: {const}"
            assert "en" in const, f"Missing English: {const}"

    def test_booking_action_is_available_as_button(self):
        """Booking is available through the dedicated appointment button/widget"""
        assert BOOK_TEXT["de"] in BOOKING_WIDGET_HTML["de"]
        assert BOOK_TEXT["en"] in BOOKING_WIDGET_HTML["en"]
        assert "booking-frame-de" in BOOKING_WIDGET_HTML["de"]
        assert "booking-frame-en" in BOOKING_WIDGET_HTML["en"]


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
