"""
Unit tests for consent constants (data_consent_constants.py)
Tests: Text presence, Link validity, Language coverage
"""
import sys
import os
import re

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from const.data_consent_constants import (
    PRIVACY_NOTICE,
    ACCEPT,
    DECLINE,
    DECLINE_MESSAGE,
    BOOK_TEXT,
    BOOKING_WIDGET_HTML,
    ADVISOR_CONTACTS,
)


class TestConsentConstants:
    """Test consent UI constants"""

    def test_all_languages_present(self):
        """All constants must have both 'de' and 'en' keys"""
        constants = [
            PRIVACY_NOTICE,
            ACCEPT,
            DECLINE,
            DECLINE_MESSAGE,
            BOOK_TEXT,
            BOOKING_WIDGET_HTML,
        ]
        
        for const in constants:
            assert "de" in const, f"Missing 'de' key in {const}"
            assert "en" in const, f"Missing 'en' key in {const}"

    def test_privacy_notice_de_content(self):
        """German privacy notice contains required elements"""
        notice = PRIVACY_NOTICE["de"]
        
        # Required by GDPR Art. 13
        assert "St.Gallen" in notice, "Missing controller name"
        assert "Gesprächsinhalte" in notice or "Daten" in notice, "Missing data processing info"
        assert "widerrufen" in notice, "Missing withdrawal notice"
        assert "nicht an Dritte" in notice, "Missing third-party disclosure info"

    def test_privacy_notice_en_content(self):
        """English privacy notice contains required elements"""
        notice = PRIVACY_NOTICE["en"]
        
        assert "St.Gallen" in notice, "Missing controller name"
        assert "conversation" in notice.lower() or "data" in notice.lower(), "Missing data processing info"
        assert "withdraw" in notice.lower(), "Missing withdrawal notice"
        assert "not shared" in notice.lower() or "third" in notice.lower(), "Missing third-party disclosure"

    def test_privacy_policy_link_valid(self):
        """Privacy policy links must be valid URLs"""
        url_pattern = r'https://[^\s\)]+'
        
        # German link
        de_matches = re.findall(url_pattern, PRIVACY_NOTICE["de"])
        assert len(de_matches) > 0, "German privacy notice missing URL"
        assert "unisg.ch" in de_matches[0], "German link should point to unisg.ch"
        
        # English link
        en_matches = re.findall(url_pattern, PRIVACY_NOTICE["en"])
        assert len(en_matches) > 0, "English privacy notice missing URL"
        assert "unisg.ch" in en_matches[0], "English link should point to unisg.ch"

    def test_links_are_not_empty(self):
        """Links must not be empty parentheses"""
        assert "()" not in PRIVACY_NOTICE["de"], "German link is empty"
        assert "()" not in PRIVACY_NOTICE["en"], "English link is empty"

    def test_decline_message_has_contact(self):
        """Decline message must provide alternative contact"""
        for lang in ["de", "en"]:
            msg = DECLINE_MESSAGE[lang]
            assert "emba@unisg.ch" in msg, f"Missing contact email in {lang} decline message"

    def test_booking_button_texts_present(self):
        """Booking button text must be localized"""
        assert BOOK_TEXT["de"] == "Termin buchen"
        assert BOOK_TEXT["en"] == "Book an appointment"

    def test_booking_widget_contains_advisors_and_slots(self):
        """Booking widget must expose advisor buttons and embedded slot frames"""
        assert BOOK_TEXT["en"] in BOOKING_WIDGET_HTML["en"]
        assert BOOK_TEXT["de"] in BOOKING_WIDGET_HTML["de"]

        for lang in ["en", "de"]:
            widget = BOOKING_WIDGET_HTML[lang]
            assert f'booking-frame-{lang}' in widget
            assert "calendly.com" in widget

            for advisor in ADVISOR_CONTACTS:
                assert advisor["name"] in widget
                assert advisor["url"] in widget


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
