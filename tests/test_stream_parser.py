"""
Offline unit tests for the streaming response-field parser.
No API key, no network. Run: pytest tests/test_stream_parser.py -v
"""
import json
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.rag.stream_parser import ResponseFieldStreamParser


def stream_through(parser: ResponseFieldStreamParser, text: str, chunk_size: int) -> str:
    """Feed `text` in chunks of `chunk_size`, return concatenated deltas."""
    out = []
    for i in range(0, len(text), chunk_size):
        out.append(parser.feed(text[i:i + chunk_size]))
    return "".join(out)


SAMPLE_JSON = json.dumps({
    "response": "Der **EMBA HSG** kostet CHF 77'500.\nFrühere Bewerbung = reduzierte Gebühr.",
    "additional_details": "Mehr Infos zur Finanzierung auf Anfrage.",
    "appointment_requested": False,
    "show_booking_widget": False,
    "relevant_programs": [],
}, ensure_ascii=False)

EXPECTED_RESPONSE = (
    "Der **EMBA HSG** kostet CHF 77'500.\nFrühere Bewerbung = reduzierte Gebühr."
)


class TestJsonMode:
    @pytest.mark.parametrize("chunk_size", [1, 2, 3, 5, 7, 16, 64, 10_000])
    def test_extracts_only_response_field_at_any_chunking(self, chunk_size):
        parser = ResponseFieldStreamParser()
        result = stream_through(parser, SAMPLE_JSON, chunk_size)
        assert result == EXPECTED_RESPONSE
        assert parser.field_complete

    def test_never_leaks_other_fields(self):
        parser = ResponseFieldStreamParser()
        result = stream_through(parser, SAMPLE_JSON, 3)
        assert "additional_details" not in result
        assert "appointment_requested" not in result
        assert "{" not in result

    def test_escaped_quotes_inside_value(self):
        payload = json.dumps({"response": 'Das Programm "emba X" ist ein Joint Degree.'})
        parser = ResponseFieldStreamParser()
        assert stream_through(parser, payload, 2) == 'Das Programm "emba X" ist ein Joint Degree.'

    def test_unicode_escapes(self):
        payload = '{"response": "Studiengeb\\u00fchr: CHF 85\'000"}'
        parser = ResponseFieldStreamParser()
        assert stream_through(parser, payload, 3) == "Studiengebühr: CHF 85'000"

    def test_response_field_not_first(self):
        payload = json.dumps({"is_context_dependent": True, "response": "Antwort hier."})
        parser = ResponseFieldStreamParser()
        assert stream_through(parser, payload, 4) == "Antwort hier."

    def test_random_chunk_boundaries_fuzz(self):
        rng = random.Random(42)
        for _ in range(25):
            parser = ResponseFieldStreamParser()
            out, i = [], 0
            while i < len(SAMPLE_JSON):
                step = rng.randint(1, 9)
                out.append(parser.feed(SAMPLE_JSON[i:i + step]))
                i += step
            assert "".join(out) == EXPECTED_RESPONSE


class TestPlainMode:
    def test_plain_text_passes_through(self):
        parser = ResponseFieldStreamParser()
        text = "Eine ganz normale Antwort ohne JSON."
        assert stream_through(parser, text, 5) == text

    def test_leading_whitespace_then_plain(self):
        parser = ResponseFieldStreamParser()
        assert stream_through(parser, "   Hallo Welt", 4) == "   Hallo Welt"


class TestEdgeCases:
    def test_empty_feeds_are_safe(self):
        parser = ResponseFieldStreamParser()
        assert parser.feed("") == ""
        assert parser.feed('{"response": "ok"}') == "ok"

    def test_nothing_emitted_before_field_starts(self):
        parser = ResponseFieldStreamParser()
        assert parser.feed('{"resp') == ""
        assert parser.feed('onse": ') == ""
        assert parser.feed('"Hal') == "Hal"
        assert parser.feed('lo"}') == "lo"
